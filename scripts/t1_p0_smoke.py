"""Local T1 P0 smoke against Compose. Writes .t1-smoke-responses.md. No GitHub."""
from __future__ import annotations

import json
import random
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:18080"
OUT = ROOT / ".t1-smoke-responses.md"
DOCX = ROOT / ".t1-smoke-input.docx"
BROKEN = ROOT / ".t1-smoke-broken.pdf"
sections: list[str] = []


def add(title: str, status: int, body: object) -> None:
    sections.append(f"## {title}\n\nstatus: {status}\n\n```json\n{json.dumps(body, ensure_ascii=False, indent=2)}\n```\n")


def request(method: str, path: str, *, token: str | None = None, json_body: object | None = None,
            form: tuple[bytes, str, str, str] | None = None, idem: str | None = None) -> tuple[int, object]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if idem:
        headers["Idempotency-Key"] = idem
    data = None
    if json_body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(json_body).encode("utf-8")
    elif form is not None:
        file_bytes, filename, content_type, role = form
        boundary = "----lexcyberSmokeBoundary"
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        parts = [
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"role\"\r\n\r\n{role}\r\n".encode(),
            (
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
                f"Content-Type: {content_type}\r\n\r\n"
            ).encode()
            + file_bytes
            + b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
        data = b"".join(parts)
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


def wait_ready() -> None:
    for _ in range(45):
        try:
            status, body = request("GET", "/healthz")
            if status == 200 and (body or {}).get("status") == "ok":
                return
        except Exception:
            pass
        time.sleep(2)
    raise SystemExit(f"service not ready at {BASE}")


def poll_task(task_id: str, token: str) -> tuple[int, dict]:
    last = (0, {})
    for _ in range(60):
        last = request("GET", f"/v1/tasks/{task_id}", token=token)
        status = (last[1] or {}).get("status")
        if status in {"completed", "failed", "timed_out", "rejected"}:
            return last
        time.sleep(2)
    return last


def main() -> None:
    wait_ready()
    if not DOCX.exists():
        raise SystemExit(f"missing {DOCX}")
    suffix = random.randint(1000, 9999)
    user_a = f"t1smoke{suffix}"
    user_b = f"t1smokeb{suffix}"
    password = "SmokePass123"

    status, body = request("POST", "/v1/auth/register", json_body={
        "username": user_a, "password": password, "displayName": "T1 Smoke A",
    })
    if status != 201:
        raise SystemExit(f"register A failed {status} {body}")
    token_a = body["token"]
    add("POST /v1/auth/register (A)", status, {"username": body.get("username"), "displayName": body.get("displayName")})

    status, body = request("POST", "/v1/auth/register", json_body={
        "username": user_b, "password": password, "displayName": "T1 Smoke B",
    })
    if status != 201:
        raise SystemExit(f"register B failed {status} {body}")
    token_b = body["token"]

    status, body = request("POST", "/v1/cases", json_body={"title": "no auth"})
    add("POST /v1/cases without bearer", status, body)
    if status != 401:
        raise SystemExit(f"expected 401 without bearer, got {status}")

    status, body = request("POST", "/v1/cases", token=token_a, json_body={
        "title": "测试案例 001",
        "jurisdiction": "CN",
        "asOfDate": "2026-09-06",
        "metadata": {
            "datasetCaseId": "001",
            "isDevelopmentSample": True,
            "relations": {"events": [{"eventId": "evt-smoke-001", "stage": "help",
                                         "documentId": "doc-pending-upload"}]},
        },
    })
    add("POST /v1/cases", status, body)
    if status != 201:
        raise SystemExit(f"create case failed {status} {body}")
    case_id = body["id"]

    status, body = request("GET", "/v1/cases?page=0&size=20", token=token_a)
    add("GET /v1/cases", status, body)
    status, body = request("GET", f"/v1/cases/{case_id}", token=token_a)
    add("GET /v1/cases/{caseId}", status, body)

    status, body = request("GET", f"/v1/cases/{case_id}", token=token_b)
    add("GET /v1/cases/{caseId} cross-user", status, body)
    if status != 404:
        raise SystemExit(f"expected 404 cross-user case, got {status}")

    docx_bytes = DOCX.read_bytes()
    status, body = request(
        "POST", f"/v1/cases/{case_id}/documents", token=token_a,
        form=(docx_bytes, "案情材料.docx",
              "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "input"),
        idem=f"upload-demo-{suffix}",
    )
    add("POST /v1/cases/{caseId}/documents input", status, body)
    if status != 201:
        raise SystemExit(f"upload failed {status} {body}")
    doc_id = body["id"]
    parse_task_id = body.get("parseTaskId")
    if not parse_task_id:
        raise SystemExit("parseTaskId missing")

    status, body = request("PATCH", f"/v1/cases/{case_id}/metadata/relations/events/evt-smoke-001/document",
                           token=token_a, json_body={"documentId": doc_id, "locator": "paragraph:1"})
    add("PATCH event document binding", status, body)
    if status != 200 or body.get("metadata", {}).get("relations", {}).get("events", [{}])[0].get("documentId") != doc_id:
        raise SystemExit(f"event document binding failed {status} {body}")

    status, body = request(
        "POST", f"/v1/cases/{case_id}/documents", token=token_a,
        form=(docx_bytes, "案情材料.docx",
              "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "input"),
        idem=f"upload-demo-{suffix}",
    )
    add("POST upload idempotent replay", status, body)
    if body.get("id") != doc_id:
        raise SystemExit("idempotent replay should return same document")

    status, body = request(
        "POST", f"/v1/cases/{case_id}/documents", token=token_a,
        form=(docx_bytes + b"different", "案情材料.docx",
              "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "input"),
        idem=f"upload-demo-{suffix}",
    )
    add("POST upload idempotent conflict", status, body)
    if status != 409:
        raise SystemExit(f"expected 409 idempotency conflict, got {status}")

    status, body = request(
        "POST", f"/v1/cases/{case_id}/documents", token=token_a,
        form=(b"plain text", "notes.txt", "text/plain", "input"),
    )
    add("POST upload unsupported type", status, body)
    if status != 415:
        raise SystemExit(f"expected 415, got {status}")

    status, body = request(
        "POST", f"/v1/cases/{case_id}/documents", token=token_a,
        form=(docx_bytes, "标注材料.docx",
              "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "annotation"),
        idem=f"ann-{suffix}",
    )
    add("POST upload annotation", status, body)
    if status != 201 or body.get("role") != "annotation":
        raise SystemExit(f"annotation upload failed {status} {body}")

    status, body = request("GET", f"/v1/cases/{case_id}/documents?role=input&page=0&size=20", token=token_a)
    add("GET /v1/cases/{caseId}/documents?role=input", status, body)
    status, body = request("GET", f"/v1/documents/{doc_id}", token=token_a)
    add("GET /v1/documents/{documentId} refresh", status, body)
    status, body = request("GET", f"/v1/documents/{doc_id}", token=token_b)
    add("GET /v1/documents/{documentId} cross-user", status, body)
    if status != 404:
        raise SystemExit(f"expected 404 cross-user document, got {status}")

    status, body = poll_task(parse_task_id, token_a)
    add("GET /v1/tasks/{parseTaskId}", status, body)
    if body.get("status") != "completed":
        raise SystemExit(f"parse did not complete: {body}")

    status, body = request("GET", f"/v1/tasks/{parse_task_id}/result", token=token_a)
    add("GET /v1/tasks/{id}/result", status, body)
    if (body.get("content") or {}).get("schemaVersion") != "document.parse.v1":
        raise SystemExit(f"unexpected schemaVersion {body}")

    status, body = request("GET", f"/v1/tasks/{parse_task_id}", token=token_b)
    add("GET /v1/tasks/{id} cross-user", status, body)
    if status != 404:
        raise SystemExit(f"expected 404 cross-user task, got {status}")

    if BROKEN.exists():
        status, body = request(
            "POST", f"/v1/cases/{case_id}/documents", token=token_a,
            form=(BROKEN.read_bytes(), "broken.pdf", "application/pdf", "input"),
            idem=f"broken-{suffix}",
        )
        fail_id = body.get("parseTaskId")
        if fail_id:
            status, body = poll_task(fail_id, token_a)
            add("GET failed parse task", status, body)
            if body.get("status") in {"failed", "timed_out"}:
                status, body = request("POST", f"/v1/tasks/{fail_id}/retry", token=token_a)
                add("POST /v1/tasks/{id}/retry", status, body)

    header = (
        "# T1 P0 smoke responses\n\n"
        f"- BaseUrl: {BASE}\n"
        f"- caseId: {case_id}\n"
        f"- documentId: {doc_id}\n"
        f"- parseTaskId: {parse_task_id}\n\n"
    )
    OUT.write_text(header + "\n".join(sections), encoding="utf-8")
    print(f"SMOKE_OK wrote {OUT}")
    print(f"caseId={case_id} parseTaskId={parse_task_id}")


if __name__ == "__main__":
    main()
