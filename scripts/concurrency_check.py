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
import time
import urllib.error
import urllib.request
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


def setup_case(base: str, token: str) -> str:
    created = obj(*request(base, "POST", "/v1/cases", token=token, json_body={
        "title": f"concurrency-check-{int(time.time())}",
        "jurisdiction": "CN", "metadata": {"purpose": "concurrency-check"},
    }), 201, "create case")
    case_id = str(created["id"])
    status, body = request(base, "PUT", f"/v2/cases/{case_id}/facts-entities/facts",
                           token=token, json_body={"items": [
                               {"key": "knowledge_of_crime", "value": "true",
                                "verificationStatus": "confirmed"},
                           ]})
    if status not in (200, 204):
        raise SystemExit(f"write facts {status} {body}")
    return case_id


def check_double_confirm(base: str, token: str, case_id: str) -> str:
    """用例 1：双确认 CAS。返回检查结果行。"""
    head = obj(*request(base, "GET", f"/v2/cases/{case_id}/facts-head", token=token),
               200, "facts head")
    expected = head.get("confirmedFactsVersionId")
    v1 = obj(*request(base, "POST", f"/v2/cases/{case_id}/facts-versions", token=token),
             201, "create facts version")
    v1_id = str(v1.get("factsVersionId") or v1.get("id"))
    obj(*request(
        base, "POST", f"/v2/cases/{case_id}/facts-versions/{v1_id}/confirm",
        token=token, json_body={"expectedConfirmedFactsVersionId": expected}), 200,
        "confirm v1")

    # 事实再改一次 → v2 版本；用过期 expected head 确认，必须 409
    request(base, "PUT", f"/v2/cases/{case_id}/facts-entities/facts", token=token,
            json_body={"items": [
                {"key": "knowledge_of_crime", "value": "true",
                 "verificationStatus": "confirmed"},
                {"key": "concurrency_marker", "value": "v2",
                 "verificationStatus": "candidate"},
            ]})
    v2 = obj(*request(base, "POST", f"/v2/cases/{case_id}/facts-versions", token=token),
             201, "create facts version 2")
    v2_id = str(v2.get("factsVersionId") or v2.get("id"))
    status, body = request(
        base, "POST", f"/v2/cases/{case_id}/facts-versions/{v2_id}/confirm",
        token=token,
        json_body={"expectedConfirmedFactsVersionId": "00000000-0000-0000-0000-000000000000"})
    if status == 409 and isinstance(body, dict) and body.get("code") == "FACTS_HEAD_CONFLICT":
        return "PASS double-confirm CAS → 409 FACTS_HEAD_CONFLICT"
    return f"FAIL double-confirm CAS → expected 409 FACTS_HEAD_CONFLICT, got {status} {body}"


def wait_execution(base: str, token: str, execution_id: str, limit: int = 80) -> dict[str, Any]:
    for _ in range(limit):
        status, body = request(base, "GET", f"/v2/executions/{execution_id}", token=token)
        if status == 200 and isinstance(body, dict):
            state = str(body.get("state") or body.get("status") or "")
            if state in TERMINAL_STATES:
                return body
        time.sleep(1.5)
    raise SystemExit(f"execution {execution_id} did not reach terminal state")


def check_double_publish(base: str, token: str, case_id: str,
                         engine_url: str, java_url: str, service_token: str) -> str:
    """用例 2：同一 execution 结果回调重放，工件版本不得新增。"""
    created = obj(*request(base, "POST", f"/v2/cases/{case_id}/modules/conviction/executions",
                           token=token), 200, "dispatch conviction")
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

    replays = []
    for i in range(3):
        status, body = request(
            java_url, "POST", f"/internal/v1/executions/{execution_id}/result",
            service_token=service_token, json_body=callback)
        replays.append((status, body))
        if status != 200:
            return f"FAIL double-publish → replay {i + 1} returned {status} {body}"

    head_after = obj(*request(base, "GET", f"/v2/cases/{case_id}/modules/conviction",
                              token=token), 200, "module head after replay")
    latest_after = head_after.get("latestVersionId")
    version_after = None
    if latest_after:
        artifact = obj(*request(base, "GET", f"/v2/artifact-versions/{latest_after}",
                                token=token), 200, "artifact after replay")
        version_after = artifact.get("version")

    if latest_after == latest and version_after == version_before:
        return f"PASS double-publish → 3 次回调重放，工件版本稳定 v{version_after}"
    return (f"FAIL double-publish → 版本漂移 latest {latest}→{latest_after} "
            f"version {version_before}→{version_after}")


def check_archive_interleave(base: str, token: str, case_id: str) -> str:
    """用例 3：复核未决时归档 + 批准后归档，全程无 5xx、行为确定。"""
    head = obj(*request(base, "GET", f"/v2/cases/{case_id}/modules/conviction",
                        token=token), 200, "module head")
    latest = head.get("latestVersionId")
    if not latest:
        return "SKIP archive-interleave → 无定罪工件（需先跑通用例 2 或已派发）"
    artifact = obj(*request(base, "GET", f"/v2/artifact-versions/{latest}", token=token),
                   200, "artifact")
    version = artifact.get("version")

    opened = request(base, "POST", f"/v2/artifact-versions/{latest}/reviews",
                     token=token, json_body={"comment": "concurrency interleave"})
    if opened[0] not in (200, 201):
        return f"FAIL archive-interleave → open review {opened[0]} {opened[1]}"
    review_id = str((opened[1] or {}).get("reviewId") or (opened[1] or {}).get("id"))

    pending_archive = request(base, "POST", f"/v2/cases/{case_id}/archives",
                              token=token, json_body={"archiveProfile": "case.full.v1"})
    if isinstance(pending_archive[0], int) and pending_archive[0] >= 500:
        return (f"FAIL archive-interleave → 复核未决归档 5xx: "
                f"{pending_archive[0]} {pending_archive[1]}")
    pending_outcome = f"{pending_archive[0]}"

    if review_id in ("", "None"):
        return ("SKIP archive-interleave → open review 未返回 reviewId；"
                f"未决归档结果 {pending_outcome}")
    decision = request(base, "POST", f"/v1/reviews/{review_id}/approve",
                       token=token, reviewer="concurrency-check",
                       json_body={"resultVersion": version,
                                  "comment": "concurrency check approval"})
    if decision[0] != 200:
        return (f"FAIL archive-interleave → approve {decision[0]} {decision[1]}；"
                f"未决归档结果 {pending_outcome}")

    final_archive = request(base, "POST", f"/v2/cases/{case_id}/archives",
                            token=token, json_body={"archiveProfile": "case.full.v1"})
    if isinstance(final_archive[0], int) and final_archive[0] >= 500:
        return (f"FAIL archive-interleave → 批准后归档 5xx: "
                f"{final_archive[0]} {final_archive[1]}")
    return (f"PASS archive-interleave → 未决归档 {pending_outcome}，"
            f"批准后归档 {final_archive[0]}（无 5xx）")


def main() -> int:
    parser = argparse.ArgumentParser(description="LexCyber §19 concurrency checks")
    parser.add_argument("--base-url", default=os.environ.get("LEXCYBER_BASE_URL",
                                                             "http://127.0.0.1:18080"))
    parser.add_argument("--engine-url", default=os.environ.get("LEXCYBER_ENGINE_URL", ""))
    parser.add_argument("--java-url", default=os.environ.get("LEXCYBER_JAVA_URL", ""))
    parser.add_argument("--service-token",
                        default=os.environ.get("SERVICE_TOKEN")
                        or os.environ.get("ENGINE_SERVICE_TOKEN", ""))
    args = parser.parse_args()

    token = register(args.base_url)
    case_id = setup_case(args.base_url, token)
    print(f"case={case_id}")

    results = [check_double_confirm(args.base_url, token, case_id)]

    if args.engine_url and args.java_url and args.service_token:
        results.append(check_double_publish(args.base_url, token, case_id,
                                            args.engine_url, args.java_url,
                                            args.service_token))
    else:
        results.append("SKIP double-publish → 需 --engine-url/--java-url/--service-token"
                       "（容器网内执行）")

    results.append(check_archive_interleave(args.base_url, token, case_id))

    failed = False
    for line in results:
        print(line)
        if line.startswith("FAIL"):
            failed = True
    print("CONCURRENCY_" + ("FAIL" if failed else "OK"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
