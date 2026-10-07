"""§19 并发/幂等验证脚本（可重复跑，不走业务流程捷径）。

覆盖三个用例：
1. 双确认 CAS：两个 FactsVersion 并发确认语义——后到者携带过期 expected head
   必须 409 FACTS_HEAD_CONFLICT，不得静默覆盖。
2. 双发布幂等：同一 execution 的结果回调重放 N 次——execution_publication
   锁内幂等重查，工件版本不得新增（ADR-0001）。需要 internal 访问。
3. 归档/复核交错：工件复核未决时归档与复核批准后归档的行为确定性，
   且全链路不出现 5xx。

公开用例（1/3）经 nginx 即可跑；用例 2 需要引擎/内部端点，必须在
compose 网络内执行：

    docker compose cp scripts/concurrency_check.py lexcyber-v03-engine-1:/tmp/
    docker compose exec engine python /tmp/concurrency_check.py \\
        --base-url http://java:8080 \\
        --engine-url http://engine:8100 --java-url http://java:8080

环境变量：SERVICE_TOKEN / ENGINE_SERVICE_TOKEN（容器内已注入）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any

TERMINAL_STATES = {"completed", "failed", "timed_out", "rejected"}


def request(base: str, method: str, path: str, *,
            token: str | None = None, service_token: str | None = None,
            reviewer: str | None = None,
            json_body: object | None = None) -> tuple[int, Any]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if service_token:
        headers["X-Service-Token"] = service_token
    if reviewer:
        headers["X-Reviewer-Id"] = reviewer
    data = None
    if json_body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            body = json.loads(raw) if raw else {"message": str(exc)}
        except json.JSONDecodeError:
            body = {"message": raw.decode("utf-8", errors="replace")}
        return exc.code, body
    except urllib.error.URLError as exc:
        return 0, {"message": str(exc)}


def obj(status: int, body: Any, expected: int, what: str) -> dict[str, Any]:
    if status != expected or not isinstance(body, dict):
        raise SystemExit(f"{what}: expected {expected}, got {status} {body}")
    return body


def register(base: str) -> str:
    username = f"conccheck{int(time.time())}{os.getpid()}"[-32:]
    status, body = request(base, "POST", "/v1/auth/register", json_body={
        "username": username, "password": "conc-check-pass-1",
        "displayName": "concurrency check",
    })
    if status not in (200, 201) or not isinstance(body, dict) or not body.get("token"):
        raise SystemExit(f"register failed {status} {body}")
    return str(body["token"])


def ci_facts(*extra: dict[str, Any]) -> list[dict[str, Any]]:
    """Facts predicates consumed by the CI synthetic rule/evaluator fixtures."""
    return [{**item, "evidenceIds": ["ci-evidence-1"]} for item in [
        {"key": "ci_case_label", "value": "concurrency-check", "verificationStatus": "confirmed"},
        {"key": "ci_confirmed_marker", "value": "yes", "verificationStatus": "confirmed"},
        {"key": "ci_compliance_flag", "value": True, "verificationStatus": "confirmed"},
        {"key": "ci_conviction_flag", "value": True, "verificationStatus": "confirmed"},
        {"key": "ci_distinction_flag", "value": True, "verificationStatus": "confirmed"},
        {"key": "ci_sentencing_flag", "value": True, "verificationStatus": "confirmed"},
        *extra,
    ]]


def setup_case(base: str, token: str) -> str:
    created = obj(*request(base, "POST", "/v1/cases", token=token, json_body={
        "title": f"concurrency-check-{int(time.time())}",
        "jurisdiction": "CN", "asOfDate": "2026-01-01", "metadata": {"purpose": "concurrency-check"},
    }), 201, "create case")
    case_id = str(created["id"])
    for kind, items in {
        "evidence": [{"id": "ci-evidence-1", "type": "document", "label": "CI fixture evidence",
                      "verificationStatus": "confirmed"}],
        "facts": ci_facts(),
        "actors": [{"id": "ci-actor-1", "type": "person", "name": "CI fixture",
                    "role": "subject", "verificationStatus": "confirmed"}],
        "events": [{"id": "ci-event-1", "date": "2026-01-01", "stage": "fixture",
                    "description": "synthetic CI event", "verificationStatus": "confirmed"}],
        "amounts": [{"id": "ci-amount-1", "kind": "crime_amount", "label": "CI fixture amount",
                     "value": "6", "currency": "CNY", "verificationStatus": "confirmed",
                     "evidenceIds": ["ci-evidence-1"]}],
        "jurisdiction-connections": [{"id": "ci-jurisdiction-1", "type": "territory",
                                       "value": "CI", "verificationStatus": "confirmed",
                                       "evidenceIds": ["ci-evidence-1"]}],
    }.items():
        status, body = request(base, "PUT", f"/v2/cases/{case_id}/facts-entities/{kind}",
                               token=token, json_body={"items": items})
        if status not in (200, 204):
            raise SystemExit(f"write {kind} {status} {body}")
    return case_id


def check_double_confirm(base: str, token: str, case_id: str) -> str:
    """用例 1：双确认 CAS。返回检查结果行。"""
    head = obj(*request(base, "GET", f"/v2/cases/{case_id}/facts-head", token=token),
               200, "facts head")
    expected = head.get("confirmedFactsVersionId")
    # Create two draft versions while the same head is still current.  Both
    # confirms below carry that exact expected head and execute concurrently.
    v1 = obj(*request(base, "POST", f"/v2/cases/{case_id}/facts-versions", token=token),
             201, "create facts version 1")
    v1_id = str(v1.get("factsVersionId") or v1.get("id"))
    request(base, "PUT", f"/v2/cases/{case_id}/facts-entities/facts", token=token,
            json_body={"items": ci_facts(
                {"key": "concurrency_marker", "value": "v2", "verificationStatus": "candidate"})})
    v2 = obj(*request(base, "POST", f"/v2/cases/{case_id}/facts-versions", token=token),
             201, "create facts version 2")
    v2_id = str(v2.get("factsVersionId") or v2.get("id"))
    def confirm(version_id: str) -> tuple[int, Any]:
        return request(base, "POST", f"/v2/cases/{case_id}/facts-versions/{version_id}/confirm",
                       token=token, json_body={"expectedConfirmedFactsVersionId": expected})

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(confirm, version_id) for version_id in (v1_id, v2_id)]
        outcomes = [future.result() for future in futures]
    winners = [(version_id, status, body) for version_id, (status, body)
               in zip((v1_id, v2_id), outcomes) if status == 200]
    conflicts = [(version_id, status, body) for version_id, (status, body)
                 in zip((v1_id, v2_id), outcomes)
                 if status == 409 and isinstance(body, dict)
                 and body.get("code") == "FACTS_HEAD_CONFLICT"]
    if len(winners) != 1 or len(conflicts) != 1:
        return f"FAIL double-confirm CAS → outcomes={outcomes}"
    head_after = obj(*request(base, "GET", f"/v2/cases/{case_id}/facts-head", token=token),
                     200, "facts head after concurrent confirm")
    winner_id = winners[0][0]
    actual = str(head_after.get("confirmedFactsVersionId"))
    if actual != winner_id:
        return f"FAIL double-confirm CAS → winner {winner_id} but head is {actual}"
    return f"PASS double-confirm CAS → winner={winner_id}, loser=409 FACTS_HEAD_CONFLICT"


def wait_execution(base: str, token: str, execution_id: str, limit: int = 80) -> dict[str, Any]:
    for _ in range(limit):
        status, body = request(base, "GET", f"/v2/executions/{execution_id}", token=token)
        if status == 200 and isinstance(body, dict):
            state = str(body.get("state") or body.get("status") or "")
            if state in TERMINAL_STATES:
                return body
        time.sleep(1.5)
    raise SystemExit(f"execution {execution_id} did not reach terminal state")


def prepare_archive_case(base: str, token: str, case_id: str) -> dict[str, Any]:
    """Build the complete case.full.v1 fixture, leaving the draft review pending."""
    modules: dict[str, dict[str, Any]] = {}
    # double-publish leaves conviction's latest review pending; approve it before
    # rendering the draft so the draft dependency snapshot is complete.
    conviction_head = obj(*request(base, "GET", f"/v2/cases/{case_id}/modules/conviction", token=token),
                          200, "conviction head")
    conviction_id = str(conviction_head.get("latestVersionId"))
    conviction = obj(*request(base, "GET", f"/v2/artifact-versions/{conviction_id}", token=token),
                     200, "conviction artifact")
    conviction_reviews = obj(*request(base, "GET", f"/v2/artifact-versions/{conviction_id}/reviews",
                                      token=token), 200, "conviction reviews")
    conviction_pending = [r for r in conviction_reviews.get("items", [])
                          if r.get("status") == "pending"]
    if len(conviction_pending) != 1:
        raise RuntimeError(f"expected one pending conviction review: {conviction_reviews}")
    decision = request(base, "POST", f"/v1/reviews/{conviction_pending[0]['reviewId']}/approve",
                       token=token, json_body={"resultVersion": conviction["version"]})
    if decision[0] != 200 or decision[1].get("status") != "approved":
        raise RuntimeError(f"approve conviction review failed: {decision}")
    modules["conviction"] = conviction

    for module in ("compliance", "sentencing"):
        dispatched = obj(*request(base, "POST", f"/v2/cases/{case_id}/modules/{module}/executions",
                                 token=token), 202, f"dispatch {module}")
        view = wait_execution(base, token, str(dispatched["executionId"]))
        if str(view.get("state") or view.get("status")) != "completed":
            raise RuntimeError(f"{module} execution did not complete: {view}")
        head = obj(*request(base, "GET", f"/v2/cases/{case_id}/modules/{module}", token=token),
                   200, f"{module} head")
        artifact_id = str(head.get("latestVersionId"))
        artifact = obj(*request(base, "GET", f"/v2/artifact-versions/{artifact_id}", token=token),
                       200, f"{module} artifact")
        if artifact.get("outcomeStatus") != "calculated":
            raise RuntimeError(f"{module} artifact is not calculated: {artifact}")
        opened = obj(*request(base, "POST", f"/v2/artifact-versions/{artifact_id}/reviews",
                              token=token, json_body={"comment": "concurrency fixture review"}),
                     201, f"open {module} review")
        decision = request(base, "POST", f"/v1/reviews/{opened['reviewId']}/approve",
                           token=token, json_body={"resultVersion": artifact["version"]})
        if decision[0] != 200 or decision[1].get("status") != "approved":
            raise RuntimeError(f"approve {module} review failed: {decision}")
        modules[module] = artifact

    rendered = obj(*request(base, "POST", f"/v2/cases/{case_id}/drafts/render", token=token,
                            json_body={"docType": "ci.review_note"}), 201, "render draft")
    wait_execution(base, token, str(rendered["executionId"]))
    draft_id = str(rendered["draftId"])
    draft_head = obj(*request(base, "GET", f"/v2/drafts/{draft_id}", token=token), 200, "draft head")
    draft_artifact_id = str(draft_head["latestVersionId"])
    draft = obj(*request(base, "GET", f"/v2/artifact-versions/{draft_artifact_id}", token=token),
                200, "draft artifact")
    if draft.get("outcomeStatus") != "calculated":
        raise RuntimeError(f"draft artifact is not calculated: {draft}")
    opened = obj(*request(base, "POST", f"/v2/artifact-versions/{draft_artifact_id}/reviews",
                          token=token, json_body={"comment": "concurrency draft review"}),
                 201, "open draft review")
    facts = obj(*request(base, "GET", f"/v2/cases/{case_id}/facts-head", token=token),
                200, "archive facts head")
    return {
        "factsVersionId": facts.get("confirmedFactsVersionId"),
        "targetArtifactId": draft_artifact_id,
        "targetVersion": draft["version"],
        "reviewId": str(opened["reviewId"]),
        "items": [{"artifactVersionId": str(item["artifactVersionId"]), "role": role}
                  for role, item in (("compliance", modules["compliance"]),
                                     ("conviction", modules["conviction"]),
                                     ("sentencing", modules["sentencing"]),
                                     ("draft", draft))],
    }


def check_double_publish(base: str, token: str, case_id: str,
                         engine_url: str, java_url: str, service_token: str) -> str:
    """用例 2：同一 execution 结果回调重放，工件版本不得新增。"""
    created = obj(*request(base, "POST", f"/v2/cases/{case_id}/modules/conviction/executions",
                           token=token), 202, "dispatch conviction")
    execution_id = str(created.get("executionId"))
    if execution_id in ("", "None"):
        return "FAIL double-publish → dispatch response missing executionId"
    view = wait_execution(base, token, execution_id)
    if str(view.get("state") or view.get("status")) != "completed":
        return f"FAIL double-publish → execution ended {view.get('state') or view.get('status')}"

    status, callback = request(
        engine_url, "GET", f"/internal/v1/executions/{execution_id}",
        service_token=service_token)
    if status != 200 or not isinstance(callback, dict):
        return f"SKIP double-publish → engine execution view unavailable: {status} {callback}"

    head_before = obj(*request(base, "GET", f"/v2/cases/{case_id}/modules/conviction",
                               token=token), 200, "module head")
    latest = head_before.get("latestVersionId")
    version_before = None
    if latest:
        artifact = obj(*request(base, "GET", f"/v2/artifact-versions/{latest}", token=token),
                       200, "artifact version")
        version_before = artifact.get("version")

    def replay(_: int) -> tuple[int, Any]:
        return request(java_url, "POST", f"/internal/v1/executions/{execution_id}/result",
                       service_token=service_token, json_body=callback)

    # Start all callbacks together so this exercises the publication lock,
    # rather than merely replaying the same request serially.
    with ThreadPoolExecutor(max_workers=3) as pool:
        replays = list(pool.map(replay, range(3)))
    for i, (status, body) in enumerate(replays):
        if status != 200:
            return f"FAIL double-publish → concurrent replay {i + 1} returned {status} {body}"

    head_after = obj(*request(base, "GET", f"/v2/cases/{case_id}/modules/conviction",
                              token=token), 200, "module head after replay")
    latest_after = head_after.get("latestVersionId")
    version_after = None
    if latest_after:
        artifact = obj(*request(base, "GET", f"/v2/artifact-versions/{latest_after}",
                                token=token), 200, "artifact after replay")
        version_after = artifact.get("version")

    reviews_status, reviews = request(base, "GET", f"/v2/artifact-versions/{latest_after}/reviews",
                                      token=token)
    if reviews_status != 200 or not isinstance(reviews, dict):
        return f"FAIL double-publish → reviews lookup {reviews_status} {reviews}"
    reviews_items = reviews.get("items")
    if not isinstance(reviews_items, list) or len(reviews_items) != 1:
        return f"FAIL double-publish → expected one review, got {reviews_items}"
    if latest_after == latest and version_after == version_before:
        return f"PASS double-publish → 3 concurrent replays, artifact/review stable v{version_after}"
    return (f"FAIL double-publish → 版本漂移 latest {latest}→{latest_after} "
            f"version {version_before}→{version_after}")


def check_archive_interleave(base: str, token: str, case_id: str,
                             context: dict[str, Any]) -> str:
    """用例 3：复核未决时归档 + 批准后归档，全程无 5xx、行为确定。"""
    version = context["targetVersion"]
    confirmed_facts = context["factsVersionId"]
    expected_items = context["items"]

    review_id = context["reviewId"]

    pending_archive = request(base, "POST", f"/v2/cases/{case_id}/archives",
                              token=token, json_body={"archiveProfile": "case.full.v1"})
    pending_body = pending_archive[1] if isinstance(pending_archive[1], dict) else {}
    if pending_archive[0] != 409 or pending_body.get("code") != "ARCHIVE_PRECONDITION_FAILED":
        return (f"FAIL archive-interleave → expected 409 ARCHIVE_PRECONDITION_FAILED, got "
                f"{pending_archive[0]} {pending_archive[1]}")
    pending_outcome = f"{pending_archive[0]}"

    if review_id in ("", "None"):
        return ("SKIP archive-interleave → open review 未返回 reviewId；"
                f"未决归档结果 {pending_outcome}")
    barrier = threading.Barrier(2)

    def approve() -> tuple[int, Any]:
        barrier.wait(timeout=10)
        return request(base, "POST", f"/v1/reviews/{review_id}/approve",
                       token=token, reviewer="concurrency-check",
                       json_body={"resultVersion": version,
                                  "comment": "concurrency check approval"})

    def race_archive() -> tuple[int, Any]:
        barrier.wait(timeout=10)
        return request(base, "POST", f"/v2/cases/{case_id}/archives",
                       token=token, json_body={"archiveProfile": "case.full.v1"})

    with ThreadPoolExecutor(max_workers=2) as pool:
        approve_future = pool.submit(approve)
        archive_future = pool.submit(race_archive)
        decision = approve_future.result()
        race_archive_result = archive_future.result()
    if decision[0] != 200:
        return (f"FAIL archive-interleave → approve {decision[0]} {decision[1]}；"
                f"未决归档结果 {pending_outcome}")
    race_status, race_body = race_archive_result
    if race_status == 409:
        race_error = race_body if isinstance(race_body, dict) else {}
        if race_error.get("code") != "ARCHIVE_PRECONDITION_FAILED":
            return f"FAIL archive-interleave → race archive 409 has wrong code: {race_body}"
    elif race_status == 201:
        if not verify_archive_manifest(race_body, case_id, confirmed_facts, expected_items):
            return f"FAIL archive-interleave → race archive manifest invalid: {race_body}"
    else:
        return f"FAIL archive-interleave → race archive unexpected {race_status} {race_body}"

    final_archive = request(base, "POST", f"/v2/cases/{case_id}/archives",
                            token=token, json_body={"archiveProfile": "case.full.v1"})
    if final_archive[0] != 201 or not isinstance(final_archive[1], dict):
        return (f"FAIL archive-interleave → expected approved archive 201, got "
                f"{final_archive[0]} {final_archive[1]}")
    archive_id = final_archive[1].get("archiveId")
    if not archive_id or not final_archive[1].get("manifestHash"):
        return f"FAIL archive-interleave → archive response lacks manifest: {final_archive[1]}"
    if not verify_archive_manifest(final_archive[1], case_id, confirmed_facts, expected_items):
        return f"FAIL archive-interleave → archive items/facts invalid: {final_archive[1]}"
    manifest_status, manifest = request(
        base, "GET", f"/v2/cases/{case_id}/archives/{archive_id}", token=token)
    if manifest_status != 200 or not isinstance(manifest, dict) \
            or manifest.get("archiveId") != archive_id \
            or manifest.get("manifestHash") != final_archive[1].get("manifestHash") \
            or not verify_archive_manifest(manifest, case_id, confirmed_facts, expected_items):
        return f"FAIL archive-interleave → manifest verification {manifest_status} {manifest}"
    return (f"PASS archive-interleave → pending 409, approve/archive race {race_status}, "
            "final archive 201 and manifest verified")


def verify_archive_manifest(body: Any, case_id: str, facts_version_id: Any,
                            expected_items: list[dict[str, str]]) -> bool:
    """Validate the complete case.full.v1 manifest."""
    if not isinstance(body, dict) or body.get("caseId") != case_id:
        return False
    if body.get("factsVersionId") != facts_version_id:
        return False
    items = body.get("items")
    return isinstance(items, list) and sorted(items, key=lambda item: (item.get("role", ""),
                                                                         item.get("artifactVersionId", ""))) == sorted(
        expected_items, key=lambda item: (item.get("role", ""), item.get("artifactVersionId", "")))


def main() -> int:
    parser = argparse.ArgumentParser(description="LexCyber §19 concurrency checks")
    parser.add_argument("--base-url", default=os.environ.get("LEXCYBER_BASE_URL",
                                                             "http://127.0.0.1:18080"))
    parser.add_argument("--engine-url", default=os.environ.get("LEXCYBER_ENGINE_URL", ""))
    parser.add_argument("--java-url", default=os.environ.get("LEXCYBER_JAVA_URL", ""))
    parser.add_argument("--service-token",
                        default=os.environ.get("SERVICE_TOKEN")
                        or os.environ.get("ENGINE_SERVICE_TOKEN", ""))
    parser.add_argument("--require-all", action="store_true",
                        help="treat any required check SKIP as a failure")
    args = parser.parse_args()

    token = register(args.base_url)
    case_id = setup_case(args.base_url, token)
    print(f"case={case_id}")

    results = [check_double_confirm(args.base_url, token, case_id)]

    archive_context = None
    if args.engine_url and args.java_url and args.service_token:
        publish_result = check_double_publish(args.base_url, token, case_id,
                                               args.engine_url, args.java_url,
                                               args.service_token)
        results.append(publish_result)
        if publish_result.startswith("PASS"):
            try:
                archive_context = prepare_archive_case(args.base_url, token, case_id)
            except Exception as exc:
                results.append(f"FAIL archive fixture preparation → {exc}")
        else:
            results.append("FAIL archive fixture preparation → double-publish prerequisite failed")
    else:
        results.append("SKIP double-publish → 需 --engine-url/--java-url/--service-token"
                       "（容器网内执行）")

    if archive_context is None:
        results.append("SKIP archive-interleave → requires completed module/draft fixture")
    else:
        results.append(check_archive_interleave(args.base_url, token, case_id, archive_context))

    failed = False
    for line in results:
        print(line)
        if line.startswith("FAIL") or (args.require_all and line.startswith("SKIP")):
            failed = True
    print("CONCURRENCY_" + ("FAIL" if failed else "OK"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
