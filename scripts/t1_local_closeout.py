"""Local T1 closeout against Compose. Username/password from env only. Do not commit secrets."""
from __future__ import annotations

import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:18080"
DOCX = ROOT / ".t1-smoke-input.docx"


def request(method: str, path: str, *, token: str | None = None, json_body: object | None = None,
            form: tuple[bytes, str, str, str] | None = None) -> tuple[int, object]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if json_body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(json_body).encode("utf-8")
    elif form is not None:
        file_bytes, filename, content_type, role = form
        boundary = "----lexcyberCloseout"
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        data = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"role\"\r\n\r\n{role}\r\n".encode()
            + (
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
                f"Content-Type: {content_type}\r\n\r\n"
            ).encode()
            + file_bytes
            + f"\r\n--{boundary}--\r\n".encode()
        )
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            body = json.loads(raw) if raw else {"message": str(exc)}
        except json.JSONDecodeError:
            body = {"message": raw.decode("utf-8", errors="replace")}
        return exc.code, body


def expect(status: int, body: object, wanted: int, label: str) -> object:
    if status != wanted:
        raise SystemExit(f"{label}: expected {wanted}, got {status} {body}")
    return body


def poll_task(task_id: str, token: str | None = None) -> dict:
    last: dict = {}
    for _ in range(60):
        status, body = request("GET", f"/v1/tasks/{task_id}", token=token)
        last = body if isinstance(body, dict) else {}
        if last.get("status") in {"completed", "failed", "timed_out", "rejected"}:
            return last
        time.sleep(2)
    raise SystemExit(f"task {task_id} did not finish: {last}")


def env_credentials() -> tuple[str, str]:
    username = os.environ.get("LEXCYBER_USERNAME", "").strip()
    password = os.environ.get("LEXCYBER_PASSWORD", "")
    if not username or not password:
        raise SystemExit(
            "LEXCYBER_USERNAME and LEXCYBER_PASSWORD are required. "
            "Reserved tasks need auth; do not hardcode credentials."
        )
    return username, password


def main() -> None:
    username, password = env_credentials()
    status, body = request("GET", "/healthz")
    expect(status, body, 200, "healthz")

    status, body = request("POST", "/v1/tasks", json_body={
        "query": "parse",
        "metadata": {"taskType": "document.parse", "storageKey": "stolen"},
    })
    expect(status, body, 401, "unauth document.parse")

    status, body = request("POST", "/v1/tasks", json_body={
        "query": "probe",
        "metadata": {"taskType": "model.probe"},
    })
    expect(status, body, 401, "unauth model.probe")

    status, body = request("POST", "/v1/tasks", json_body={
        "query": "local stub task",
        "metadata": {"source": "local-closeout"},
    })
    stub = expect(status, body, 202, "public stub create")
    stub_id = stub["id"]

    status, body = request("GET", f"/v1/tasks/{stub_id}")
    expect(status, body, 200, "public stub get")

    status, body = request("POST", "/v1/tasks", json_body={
        "query": "sentencing",
        "metadata": {"taskType": "sentencing.calculate"},
    })
    expect(status, body, 501, "sentencing gated")

    status, body = request("POST", "/v1/auth/login", json_body={
        "username": username, "password": password,
    })
    token_a = expect(status, body, 200, "login")["token"]
    suffix = random.randint(1000, 9999)
    status, body = request("POST", "/v1/auth/register", json_body={
        "username": f"t1closeb{suffix}",
        "password": f"Cb{random.randint(100000, 999999)}x",
        "displayName": "Closeout B",
    })
    token_b = expect(status, body, 201, "register B")["token"]

    status, body = request("POST", "/v1/cases", token=token_a, json_body={
        "title": "closeout case", "jurisdiction": "CN",
    })
    case_id = expect(status, body, 201, "create case")["id"]

    status, body = request("GET", f"/v1/cases/{case_id}/facts")
    expect(status, body, 401, "unauth facts")
    status, body = request("GET", f"/v1/cases/{case_id}/facts", token=token_b)
    expect(status, body, 404, "cross-user facts")

    status, body = request("PUT", f"/v1/cases/{case_id}/facts", token=token_a, json_body={
        "items": [{"id": "f1", "key": "amount", "value": "100", "locator": "p1", "sourceDocumentId": "doc-1"}],
    })
    expect(status, body, 200, "put facts")
    status, body = request("POST", f"/v1/cases/{case_id}/facts/confirm", token=token_a)
    expect(status, body, 200, "confirm facts")
    if body.get("status") != "confirmed":
        raise SystemExit(f"facts not confirmed: {body}")
    status, body = request("PUT", f"/v1/cases/{case_id}/facts", token=token_a, json_body={
        "items": [{"id": "f2", "key": "amount", "value": "200", "locator": "p1", "sourceDocumentId": "doc-1"}],
    })
    expect(status, body, 409, "confirmed facts locked")

    status, body = request("POST", "/v1/sources/search", token=token_a, json_body={"query": "民法典"})
    expect(status, body, 501, "source search gated")

    status, body = request("POST", "/v1/tasks", token=token_a, json_body={
        "query": "model probe",
        "metadata": {"taskType": "model.probe"},
    })
    probe = expect(status, body, 202, "auth model.probe")
    probe_status = poll_task(probe["id"], token_a)
    if probe_status.get("status") != "completed":
        raise SystemExit(f"real model.probe failed: {probe_status}")
    status, result = request("GET", f"/v1/tasks/{probe['id']}/result", token=token_a)
    expect(status, result, 200, "model.probe result")
    content = result.get("content") or {}
    if content.get("provider") in (None, "stub"):
        raise SystemExit(f"model.probe used stub, expected real API: {content}")
    print(
        "REAL_PROBE_OK "
        f"taskId={probe['id']} provider={content.get('provider')} "
        f"model={content.get('model')} latencyMs={content.get('latencyMs')}"
    )

    if not DOCX.exists():
        raise SystemExit(f"missing {DOCX}")
    status, body = request(
        "POST", f"/v1/cases/{case_id}/documents", token=token_a,
        form=(DOCX.read_bytes(), "案情材料.docx",
              "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "input"),
    )
    uploaded = expect(status, body, 201, "upload")
    doc_id = uploaded["id"]
    parse_id = uploaded.get("parseTaskId")
    if not parse_id:
        raise SystemExit("parseTaskId missing")

    status, body = request("POST", "/v1/tasks", token=token_a, json_body={
        "query": "解析指定材料，提取正文、段落、表格和原文定位",
        "caseId": "",
        "metadata": {
            "taskType": "document.parse",
            "documentId": doc_id,
            "storageKey": "stolen-key",
        },
    })
    bound = expect(status, body, 202, "owned storageKey bind")
    if bound.get("caseId") != case_id:
        raise SystemExit(f"parse did not bind owned caseId: {bound}")

    parse_status = poll_task(parse_id, token_a)
    if parse_status.get("status") != "completed":
        raise SystemExit(f"upload parse failed: {parse_status}")
    status, result = request("GET", f"/v1/tasks/{parse_id}/result", token=token_a)
    expect(status, result, 200, "parse result")
    if (result.get("content") or {}).get("schemaVersion") != "document.parse.v1":
        raise SystemExit(f"unexpected parse schema: {result}")

    bound_status = poll_task(bound["id"], token_a)
    if bound_status.get("status") != "completed":
        raise SystemExit(f"bound parse failed, client storageKey was not overwritten: {bound_status}")

    stub_poll = poll_task(stub_id)
    if stub_poll.get("status") != "completed":
        raise SystemExit(f"stub task failed: {stub_poll}")

    print("LOCAL_CLOSEOUT_OK")
    print(f"caseId={case_id} documentId={doc_id} parseTaskId={parse_id} boundTaskId={bound['id']}")


if __name__ == "__main__":
    main()
