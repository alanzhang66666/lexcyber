"""Exercise the Compose stack through nginx, including authenticated artifact review."""

from __future__ import annotations

import io
import json
import secrets
import sys
import time
import urllib.error
import urllib.request
import uuid
import zipfile

BASE = "http://127.0.0.1:18080"
SAMPLE_TEXT = "LexCyber CI document storage and parsing check."
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def request(method, path, *, token=None, payload=None, data=None, content_type=None, expected=200):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        data = json.dumps(payload).encode()
        content_type = "application/json"
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, raw = error.code, error.read()
    if status != expected:
        raise RuntimeError(f"{method} {path}: expected {expected}, got {status}: {raw.decode(errors='replace')}")
    return json.loads(raw) if raw else {}


def wait_ready():
    for _ in range(60):
        try:
            if request("GET", "/healthz").get("status") == "ok":
                return
        except (urllib.error.URLError, TimeoutError, RuntimeError):
            pass
        time.sleep(2)
    raise RuntimeError("API did not become healthy")


def wait_task(task_id, expected="completed", token=None):
    for _ in range(60):
        task = request("GET", f"/v1/tasks/{task_id}", token=token)
        if task["status"] == expected:
            return task
        if task["status"] in {"completed", "failed", "timed_out", "rejected", "waiting_review"}:
            raise RuntimeError(f"Task expected {expected}: {task}")
        time.sleep(2)
    raise RuntimeError(f"Task did not reach {expected}: {task}")


def document_form():
    """Create a minimal, valid DOCX fixture without additional runner dependencies."""
    document = io.BytesIO()
    with zipfile.ZipFile(document, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", (
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '</Types>'
        ))
        archive.writestr("_rels/.rels", (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Target="word/document.xml" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"/>'
            '</Relationships>'
        ))
        archive.writestr("word/document.xml", (
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f'<w:body><w:p><w:r><w:t>{SAMPLE_TEXT}</w:t></w:r></w:p></w:body></w:document>'
        ))
    boundary = "lexcyber-ci-" + uuid.uuid4().hex
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="role"\r\n\r\ninput\r\n'
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="ci.docx"\r\n'
        f'Content-Type: {DOCX_TYPE}\r\n\r\n'
    ).encode() + document.getvalue() + f"\r\n--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def main():
    wait_ready()
    generic = request("POST", "/v1/tasks", expected=202, payload={
        "query": "ci generic task", "metadata": {"source": "ci"},
    })
    wait_task(generic["id"])
    print("PASS generic stub task completed", flush=True)

    review_task = request("POST", "/v1/tasks", expected=202, payload={
        "query": "ci review task", "metadata": {"demo_requires_review": True},
    })
    wait_task(review_task["id"], "waiting_review")
    request("GET", "/v1/reviews?status=pending", expected=401)
    print("PASS stub review signal and unauthenticated review rejection", flush=True)

    session = request("POST", "/v1/auth/register", expected=201, payload={
        "username": "ci_smoke_" + uuid.uuid4().hex[:12],
        "password": secrets.token_urlsafe(24), "displayName": "CI smoke",
    })
    token = session["token"]
    case = request("POST", "/v1/cases", token=token, expected=201, payload={
        "title": "CI artifact review", "jurisdiction": "CN",
    })
    data, content_type = document_form()
    document = request("POST", f"/v1/cases/{case['id']}/documents", token=token,
                       expected=201, data=data, content_type=content_type)
    wait_task(document["parseTaskId"], token=token)
    result = request("GET", f"/v1/tasks/{document['parseTaskId']}/result", token=token)
    assert result["content"]["text"] == SAMPLE_TEXT, result
    print("PASS MinIO upload, document parsing and artifact publication", flush=True)

    artifact_id = result["resultId"]
    opened = request("POST", f"/v2/artifact-versions/{artifact_id}/reviews", token=token,
                     expected=201, payload={"comment": "CI artifact review"})
    review_id = opened["reviewId"]
    pending = request("GET", "/v1/reviews?status=pending", token=token)
    assert any(item["id"] == review_id for item in pending["items"]), pending
    approved = request("POST", f"/v1/reviews/{review_id}/approve", token=token,
                       payload={"resultVersion": result["version"]})
    assert approved["status"] == "approved", approved
    saved = request("GET", f"/v1/reviews/{review_id}", token=token)
    assert saved["status"] == "approved" and saved["artifactVersionId"] == artifact_id, saved
    print("PASS authenticated review approved and persisted for the published artifact", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, RuntimeError, urllib.error.URLError, TimeoutError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
