import threading
from threading import BrokenBarrierError

import pytest

from scripts import concurrency_check as check


def test_double_confirm_executes_two_requests_and_checks_winner(monkeypatch):
    calls = []
    barrier = threading.Barrier(2)
    confirmed = [None]

    def fake_request(base, method, path, **kwargs):
        calls.append((method, path))
        if method == "GET" and path.endswith("/facts-head"):
            return 200, {"confirmedFactsVersionId": confirmed[0]}
        if method == "PUT":
            return 200, {}
        if method == "POST" and path.endswith("/facts-versions"):
            version = "11111111-1111-1111-1111-111111111111" if not any(
                p.endswith("/facts-versions") for _, p in calls[:-1]) else "22222222-2222-2222-2222-222222222222"
            return 201, {"factsVersionId": version}
        if method == "POST" and "/confirm" in path:
            try:
                barrier.wait(timeout=2)
            except BrokenBarrierError:
                raise AssertionError("confirm calls were not concurrent")
            if path.endswith("11111111-1111-1111-1111-111111111111/confirm"):
                confirmed[0] = "11111111-1111-1111-1111-111111111111"
                return 200, {}
            return 409, {"code": "FACTS_HEAD_CONFLICT"}
        raise AssertionError((method, path))

    monkeypatch.setattr(check, "request", fake_request)
    result = check.check_double_confirm("http://java", "token", "case")
    assert result.startswith("PASS double-confirm CAS")
    assert sum(1 for method, path in calls if method == "POST" and "/confirm" in path) == 2


def test_double_publish_replays_are_concurrent_and_review_stable(monkeypatch):
    replay_barrier = threading.Barrier(3)
    replay_threads = set()

    def fake_request(base, method, path, **kwargs):
        if method == "POST" and path.endswith("/modules/conviction/executions"):
            return 202, {"executionId": "exec-1"}
        if method == "GET" and path == "/v2/executions/exec-1":
            return 200, {"state": "completed"}
        if method == "GET" and path == "/internal/v1/executions/exec-1":
            return 200, {"executionId": "exec-1", "status": "completed"}
        if method == "GET" and path == "/v2/cases/case/modules/conviction":
            return 200, {"latestVersionId": "version-1"}
        if method == "GET" and path == "/v2/artifact-versions/version-1":
            return 200, {"version": 1}
        if method == "POST" and path == "/internal/v1/executions/exec-1/result":
            replay_threads.add(threading.get_ident())
            replay_barrier.wait(timeout=2)
            return 200, {"status": "accepted"}
        if method == "GET" and path == "/v2/artifact-versions/version-1/reviews":
            return 200, {"items": [{"reviewId": "review-1", "status": "pending"}]}
        raise AssertionError((method, path))

    monkeypatch.setattr(check, "request", fake_request)
    result = check.check_double_publish("http://java", "token", "case", "http://engine",
                                       "http://java", "service-token")
    assert result.startswith("PASS double-publish")
    assert len(replay_threads) == 3


def test_require_all_turns_skip_into_failure(monkeypatch):
    monkeypatch.setattr(check, "register", lambda _: "token")
    monkeypatch.setattr(check, "setup_case", lambda *_: "case")
    monkeypatch.setattr(check, "check_double_confirm", lambda *_: "PASS confirm")
    monkeypatch.setattr(check, "check_double_publish", lambda *_: "SKIP publish")
    monkeypatch.setattr(check, "check_archive_interleave", lambda *_: "PASS archive")
    monkeypatch.setattr(check.sys, "argv", ["concurrency_check.py", "--require-all"])

    assert check.main() == 1


@pytest.mark.parametrize("race_result", [
    (201, {"caseId": "case", "factsVersionId": "facts-1",
           "items": [{"artifactVersionId": "wrong", "role": "conviction"}]}),
    (409, {"code": "WRONG_PRECONDITION"}),
])
def test_archive_race_is_concurrent_and_rejects_invalid_outcome(monkeypatch, race_result):
    barrier_threads = set()
    race_barrier = threading.Barrier(2)
    archive_calls = [0]

    def fake_request(base, method, path, **kwargs):
        if method == "GET" and path.endswith("/modules/conviction"):
            return 200, {"latestVersionId": "version-1"}
        if method == "GET" and path.endswith("/artifact-versions/version-1"):
            return 200, {"version": 1}
        if method == "GET" and path.endswith("/facts-head"):
            return 200, {"confirmedFactsVersionId": "facts-1"}
        if method == "GET" and path.endswith("/reviews"):
            return 200, {"items": [{"reviewId": "review-1", "status": "pending"}]}
        if method == "POST" and path.endswith("/archives"):
            archive_calls[0] += 1
            if archive_calls[0] == 1:
                return 409, {"code": "ARCHIVE_PRECONDITION_FAILED"}
            barrier_threads.add(threading.get_ident())
            race_barrier.wait(timeout=2)
            return race_result
        if method == "POST" and path.endswith("/review-1/approve"):
            barrier_threads.add(threading.get_ident())
            race_barrier.wait(timeout=2)
            return 200, {"status": "approved"}
        raise AssertionError((method, path))

    monkeypatch.setattr(check, "request", fake_request)
    result = check.check_archive_interleave("http://java", "token", "case")
    assert result.startswith("FAIL archive-interleave")
    assert len(barrier_threads) == 2


def test_archive_manifest_requires_single_confirmed_conviction_item():
    assert check.verify_archive_manifest(
        {"caseId": "case", "factsVersionId": "facts",
         "items": [{"artifactVersionId": "version", "role": "conviction"}]},
        "case", "version", "facts")
    assert not check.verify_archive_manifest(
        {"caseId": "case", "factsVersionId": "facts",
         "items": [{"artifactVersionId": "other", "role": "conviction"}]},
        "case", "version", "facts")
