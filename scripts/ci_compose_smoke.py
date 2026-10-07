"""Exercise the Compose stack through nginx, including authenticated artifact review."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

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
    accepted = expected if isinstance(expected, tuple) else (expected,)
    if status not in accepted:
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


def _id(view, *names):
    for name in names:
        if view.get(name):
            return str(view[name])
    raise RuntimeError(f"response has no identifier {names}: {view}")


def _sorted_items(items):
    return sorted(items, key=lambda item: (str(item.get("artifactVersionId")), str(item.get("role"))))


def export_docx(token, case_id, artifact_id, body):
    """Validate the real nginx → Java → Engine → MinIO export path."""
    path = f"/v2/cases/{case_id}/artifact-versions/{artifact_id}/export.docx"
    req = urllib.request.Request(BASE + path, headers={
        "Authorization": f"Bearer {token}", "Accept": DOCX_TYPE,
    })
    with urllib.request.urlopen(req, timeout=30) as response:
        assert response.status == 200
        assert response.headers.get_content_type() == DOCX_TYPE, response.headers
        assert "attachment" in response.headers.get("Content-Disposition", "")
        assert "no-store" in response.headers.get("Cache-Control", "")
        raw = response.read()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        assert archive.testzip() is None
        content_types = archive.read("[Content_Types].xml")
        assert b"wordprocessingml.document.main+xml" in content_types
        root = ET.fromstring(archive.read("word/document.xml"))
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs = []
    for paragraph in root.iter(ns + "p"):
        parts = []
        for node in paragraph.iter():
            if node.tag == ns + "t":
                parts.append(node.text or "")
            elif node.tag == ns + "tab":
                parts.append("\t")
            elif node.tag in (ns + "br", ns + "cr"):
                parts.append("\n")
        paragraphs.append("".join(parts))
    text = "\n".join(paragraphs)
    # Title, auxiliary label and final immutable provenance are the only additions.
    assert len(paragraphs) >= 3 and paragraphs[1] == "文书辅助稿，不替代司法裁量", text
    assert paragraphs[-1].startswith("来源工件版本："), text
    assert "\n".join(paragraphs[2:-1]) == body.replace("\r\n", "\n").replace("\r", "\n"), text
    assert artifact_id in text, text
    assert "文书辅助稿" in text and "不替代司法裁量" in text, text
    return raw


def wait_execution(token, execution_id):
    for _ in range(90):
        view = request("GET", f"/v2/executions/{execution_id}", token=token)
        state = view.get("state") or view.get("status")
        if state == "completed":
            return view
        if state in {"failed", "timed_out", "rejected"}:
            raise RuntimeError(f"execution {execution_id} ended {state}: {view}")
        time.sleep(1)
    raise RuntimeError(f"execution {execution_id} did not complete")


def run_lifecycle(token):
    """Exercise the v2 facts → modules → draft → archive chain through nginx."""
    case = request("POST", "/v1/cases", token=token, expected=201, payload={
        "title": "CI synthetic lifecycle fixture", "jurisdiction": "CI",
        "metadata": {"purpose": "LEXCYBER_CI_FIXTURES"},
    })
    case_id = _id(case, "id", "caseId")
    facts = [
        {"key": "ci_case_label", "value": "compose-lifecycle", "verificationStatus": "confirmed"},
        {"key": "ci_confirmed_marker", "value": "yes", "verificationStatus": "confirmed"},
        {"key": "ci_compliance_flag", "value": True, "verificationStatus": "confirmed"},
        {"key": "ci_conviction_flag", "value": True, "verificationStatus": "confirmed"},
        {"key": "ci_distinction_flag", "value": True, "verificationStatus": "confirmed"},
        {"key": "ci_sentencing_flag", "value": True, "verificationStatus": "confirmed"},
    ]
    actors = [{"id": "ci-actor-1", "type": "person", "name": "CI fixture", "role": "subject",
               "verificationStatus": "confirmed"}]
    events = [{"id": "ci-event-1", "date": "2026-01-01", "stage": "fixture",
               "description": "synthetic CI event", "verificationStatus": "confirmed"}]
    evidence = [{"id": "ci-evidence-1", "type": "document", "label": "CI fixture evidence",
                 "verificationStatus": "confirmed"}]
    amounts = [{"id": "ci-amount-1", "kind": "crime_amount", "label": "CI fixture amount",
                "value": "6", "currency": "CNY", "verificationStatus": "confirmed"}]
    jurisdiction = [{"id": "ci-jurisdiction-1", "type": "territory", "value": "CI",
                     "verificationStatus": "confirmed"}]
    for kind, items in (("facts", facts), ("actors", actors), ("events", events),
                        ("evidence", evidence), ("amounts", amounts),
                        ("jurisdiction-connections", jurisdiction)):
        request("PUT", f"/v2/cases/{case_id}/facts-entities/{kind}", token=token,
                expected=200, payload={"items": items})

    version_one = request("POST", f"/v2/cases/{case_id}/facts-versions", token=token, expected=201)
    version_one_id = _id(version_one, "factsVersionId")
    request("POST", f"/v2/cases/{case_id}/facts-versions/{version_one_id}/confirm",
            token=token, expected=200, payload={"expectedConfirmedFactsVersionId": None})
    head_one = request("GET", f"/v2/cases/{case_id}/facts-head", token=token)
    assert str(head_one["confirmedFactsVersionId"]) == version_one_id, head_one

    request("PUT", f"/v2/cases/{case_id}/facts-entities/facts", token=token,
            expected=200, payload={"items": facts + [{
                "key": "ci_clone_marker", "value": "draft", "verificationStatus": "candidate"}]})
    version_two = request("POST", f"/v2/cases/{case_id}/facts-versions", token=token, expected=201)
    version_two_id = _id(version_two, "factsVersionId")
    wrong_status = request("POST", f"/v2/cases/{case_id}/facts-versions/{version_two_id}/confirm",
                           token=token, expected=409,
                           payload={"expectedConfirmedFactsVersionId": str(uuid.uuid4())})
    assert wrong_status.get("code") == "FACTS_HEAD_CONFLICT", wrong_status
    diff = request("GET", f"/v2/cases/{case_id}/facts-versions/{version_two_id}/diff?against={version_one_id}", token=token)
    assert "sections" in diff and str(diff["toFactsVersionId"]) == version_two_id, diff
    history = request("GET", f"/v2/cases/{case_id}/facts-versions", token=token)
    history_ids = {str(item["factsVersionId"]) for item in history["items"]}
    assert {version_one_id, version_two_id}.issubset(history_ids), history
    request("POST", f"/v2/cases/{case_id}/facts-versions/{version_one_id}/clone",
            token=token, expected=200)
    head_after_clone = request("GET", f"/v2/cases/{case_id}/facts-head", token=token)
    assert str(head_after_clone["confirmedFactsVersionId"]) == version_one_id, head_after_clone
    version_detail = request("GET", f"/v2/cases/{case_id}/facts-versions/{version_one_id}", token=token)
    entities = version_detail["payload"]["entities"]
    assert all(entities.get(key) for key in (
        "actors", "events", "evidence", "amounts", "jurisdictionConnections")), version_detail
    print("PASS v2 facts versions, CAS confirmation, diff and clone head invariants", flush=True)

    modules = {}
    for module in ("compliance", "conviction", "sentencing"):
        dispatched = request("POST", f"/v2/cases/{case_id}/modules/{module}/executions",
                            token=token, expected=202)
        execution_id = _id(dispatched, "executionId")
        wait_execution(token, execution_id)
        head = request("GET", f"/v2/cases/{case_id}/modules/{module}", token=token)
        artifact_id = _id(head, "latestVersionId")
        artifact = request("GET", f"/v2/artifact-versions/{artifact_id}", token=token)
        payload = artifact["payload"]
        assert artifact["artifactVersionId"] == artifact_id
        assert artifact["outcomeStatus"] == "calculated" and payload["status"] == "calculated", artifact
        if module == "sentencing":
            results = payload.get("results") or []
            assert results and results[0]["status"] == "calculated" and results[0]["term_months"] == 6, artifact
        opened = request("POST", f"/v2/artifact-versions/{artifact_id}/reviews", token=token,
                         expected=201, payload={"comment": "CI synthetic fixture review"})
        review_id = _id(opened, "reviewId")
        approved = request("POST", f"/v1/reviews/{review_id}/approve", token=token,
                           payload={"resultVersion": artifact["version"]})
        assert approved.get("status") == "approved", approved
        modules[module] = artifact
    for module in ("compliance", "conviction", "sentencing"):
        confirmed_head = request("GET", f"/v2/cases/{case_id}/modules/{module}", token=token)
        assert confirmed_head["effectivelyConfirmed"] is True, confirmed_head
    print("PASS compliance, conviction and sentencing execution/publication/review", flush=True)

    render = request("POST", f"/v2/cases/{case_id}/drafts/render", token=token,
                     expected=201, payload={"docType": "ci.review_note"})
    draft_id = _id(render, "draftId")
    wait_execution(token, _id(render, "executionId"))
    streams = request("GET", f"/v2/cases/{case_id}/drafts", token=token)
    entries = [row for row in streams.get("items", []) if str(row.get("draftId")) == draft_id]
    assert len(entries) == 1, streams
    draft_head = request("GET", f"/v2/drafts/{draft_id}", token=token)
    draft_artifact_id = _id(draft_head, "latestVersionId")
    draft_artifact = request("GET", f"/v2/artifact-versions/{draft_artifact_id}", token=token)
    assert draft_artifact["outcomeStatus"] == "calculated", draft_artifact
    assert draft_artifact["payload"]["status"] == "rendered" and draft_artifact["payload"]["body"], draft_artifact
    exported = export_docx(token, case_id, draft_artifact_id, draft_artifact["payload"]["body"])
    assert export_docx(token, case_id, draft_artifact_id, draft_artifact["payload"]["body"]) == exported
    request("GET", f"/v2/cases/{case_id}/artifact-versions/{draft_artifact_id}/export.docx", expected=401)
    print("PASS rendered DOCX download, exact body/version and deterministic bytes", flush=True)
    dependencies = draft_artifact.get("dependencySnapshot", {}).get("artifacts", [])
    dependency_ids = {str(item.get("artifactVersionId")) for item in dependencies}
    assert dependency_ids == {str(modules["compliance"]["artifactVersionId"]),
                              str(modules["conviction"]["artifactVersionId"]),
                              str(modules["sentencing"]["artifactVersionId"])}, draft_artifact
    draft_review = request("POST", f"/v2/artifact-versions/{draft_artifact_id}/reviews", token=token,
                           expected=201, payload={"comment": "CI synthetic draft review"})
    request("POST", f"/v1/reviews/{_id(draft_review, 'reviewId')}/approve", token=token,
            payload={"resultVersion": draft_artifact["version"]})
    print("PASS stable draft identity, exact artifact dependencies and approved render", flush=True)

    archive = request("POST", f"/v2/cases/{case_id}/archives", token=token,
                      expected=201, payload={"archiveProfile": "case.full.v1"})
    archive_id = _id(archive, "archiveId")
    saved = request("GET", f"/v2/cases/{case_id}/archives/{archive_id}", token=token)
    assert saved["manifestHash"] == archive["manifestHash"]
    assert _sorted_items(saved["items"]) == _sorted_items(archive["items"]), saved
    render_again = request("POST", f"/v2/cases/{case_id}/drafts/render", token=token,
                           expected=201, payload={"docType": "ci.review_note"})
    assert _id(render_again, "draftId") == draft_id, render_again
    wait_execution(token, _id(render_again, "executionId"))
    current_draft_head = request("GET", f"/v2/drafts/{draft_id}", token=token)
    assert str(current_draft_head["latestVersionId"]) != draft_artifact_id, current_draft_head
    request("PUT", f"/v2/cases/{case_id}/facts-entities/facts", token=token,
            expected=200, payload={"items": facts + [{
                "key": "ci_after_archive_edit", "value": "changed", "verificationStatus": "candidate"}]})
    stale_version = request("POST", f"/v2/cases/{case_id}/facts-versions", token=token, expected=201)
    stale_id = _id(stale_version, "factsVersionId")
    request("POST", f"/v2/cases/{case_id}/facts-versions/{stale_id}/confirm", token=token,
            expected=200, payload={"expectedConfirmedFactsVersionId": version_one_id})
    stale_head = request("GET", f"/v2/cases/{case_id}/modules/compliance", token=token)
    assert stale_head["stale"] is True, stale_head
    historical_export = export_docx(token, case_id, draft_artifact_id, draft_artifact["payload"]["body"])
    assert historical_export == exported
    assert request("GET", f"/v2/artifact-versions/{draft_artifact_id}", token=token) == draft_artifact
    print("PASS historical stale DOCX retains identical bytes without changing the artifact", flush=True)
    request("POST", f"/v2/cases/{case_id}/archives", token=token,
            expected=409, payload={"archiveProfile": "case.full.v1"})
    print("PASS facts change propagates stale and blocks a mixed archive", flush=True)
    blocked_render = request("POST", f"/v2/cases/{case_id}/drafts/render", token=token,
                             expected=201, payload={"docType": "ci.blocked_note"})
    wait_execution(token, _id(blocked_render, "executionId"))
    blocked_head = request("GET", f"/v2/drafts/{_id(blocked_render, 'draftId')}", token=token)
    blocked_artifact = request("GET", f"/v2/artifact-versions/{_id(blocked_head, 'latestVersionId')}", token=token)
    assert blocked_artifact["outcomeStatus"] == "blocked"
    assert blocked_artifact["payload"]["status"] == "blocked" and blocked_artifact["payload"]["body"] is None, blocked_artifact
    blocked_export = request("GET", f"/v2/cases/{case_id}/artifact-versions/{blocked_artifact['artifactVersionId']}/export.docx",
                             token=token, expected=409)
    assert blocked_export.get("code") == "DRAFT_EXPORT_BLOCKED", blocked_export
    print("PASS unresolved template fails closed without a document body", flush=True)
    other = request("POST", "/v1/auth/register", expected=201, payload={
        "username": "ci_other_" + uuid.uuid4().hex[:12],
        "password": secrets.token_urlsafe(24), "displayName": "CI other account",
    })
    request("GET", f"/v2/cases/{case_id}/facts-head", token=other["token"], expected=404)
    request("GET", f"/v2/cases/{case_id}/artifact-versions/{draft_artifact_id}/export.docx",
            token=other["token"], expected=404)
    other_case = request("POST", "/v1/cases", token=token, expected=201,
                         payload={"title": "CI cross-case export isolation", "jurisdiction": "CI"})
    request("GET", f"/v2/cases/{other_case['id']}/artifact-versions/{draft_artifact_id}/export.docx",
            token=token, expected=404)
    print("PASS archive create/read manifest consistency and cross-account denial", flush=True)

    manual_body = "人工辅助稿\n被告人张某，涉案金额 100 元。\nA&B <source>\t核对来源。"
    manual = request("POST", f"/v1/cases/{case_id}/drafts", token=token, expected=201,
                     payload={"draftType": "手工核对记录", "body": manual_body})
    manual_artifact_id = _id(manual, "artifactVersionId")
    manual_export = export_docx(token, case_id, manual_artifact_id, manual_body)
    updated = request("PUT", f"/v1/cases/{case_id}/drafts/{manual['id']}", token=token,
                      payload={"body": manual_body + "\n第二版补充。", "version": manual["version"]})
    assert _id(updated, "artifactVersionId") != manual_artifact_id
    assert hashlib.sha256(export_docx(token, case_id, manual_artifact_id, manual_body)).digest() == hashlib.sha256(manual_export).digest()
    export_docx(token, case_id, _id(updated, "artifactVersionId"), updated["body"])
    for body in ("", "待核对【案件来源】"):
        unavailable = request("POST", f"/v1/cases/{case_id}/drafts", token=token, expected=201,
                              payload={"draftType": "未完整辅助稿", "body": body})
        error = request("GET", f"/v2/cases/{case_id}/artifact-versions/{unavailable['artifactVersionId']}/export.docx",
                        token=token, expected=409)
        assert error.get("code") == "DRAFT_EXPORT_BLOCKED", error
    print("PASS manual DOCX exact historical version, UTF-8/XML text and incomplete export denial", flush=True)

    # Confirming the entire facts version must not mark a candidate connection
    # verified. Exercise both absence and candidate state through the real engine.
    jurisdiction_case = request("POST", "/v1/cases", token=token, expected=201, payload={
        "title": "CI unverified jurisdiction fixture", "jurisdiction": "CI",
        "metadata": {"purpose": "LEXCYBER_CI_FIXTURES"},
    })
    jurisdiction_case_id = _id(jurisdiction_case, "id", "caseId")
    request("PUT", f"/v2/cases/{jurisdiction_case_id}/facts-entities/facts", token=token,
            payload={"items": facts})
    previous_facts = None
    for connections in ([], [{**jurisdiction[0], "verificationStatus": "candidate"}]):
        request("PUT", f"/v2/cases/{jurisdiction_case_id}/facts-entities/jurisdiction-connections",
                token=token, payload={"items": connections})
        facts_version = request("POST", f"/v2/cases/{jurisdiction_case_id}/facts-versions",
                                token=token, expected=201)
        facts_id = _id(facts_version, "factsVersionId")
        request("POST", f"/v2/cases/{jurisdiction_case_id}/facts-versions/{facts_id}/confirm",
                token=token, payload={"expectedConfirmedFactsVersionId": previous_facts})
        previous_facts = facts_id
        dispatched = request("POST", f"/v2/cases/{jurisdiction_case_id}/modules/conviction/executions",
                             token=token, expected=202)
        wait_execution(token, _id(dispatched, "executionId"))
        head = request("GET", f"/v2/cases/{jurisdiction_case_id}/modules/conviction", token=token)
        artifact_id = _id(head, "latestVersionId")
        artifact = request("GET", f"/v2/artifact-versions/{artifact_id}", token=token)
        assert artifact["outcomeStatus"] == "blocked" and artifact["payload"]["status"] == "blocked", artifact
        assert any(item.get("code") == "JURISDICTION_CONNECTION_UNCONFIRMED"
                   for item in artifact["payload"]["blockers"]), artifact
        review = request("POST", f"/v2/artifact-versions/{artifact_id}/reviews", token=token,
                         expected=201, payload={"comment": "CI blocked jurisdiction fixture"})
        error = request("POST", f"/v1/reviews/{_id(review, 'reviewId')}/approve", token=token,
                        expected=409, payload={"resultVersion": artifact["version"]})
        assert error.get("code") == "MODULE_BLOCKED", error
        assert not request("GET", f"/v2/cases/{jurisdiction_case_id}/modules/conviction",
                           token=token)["effectivelyConfirmed"]
    print("PASS absent/candidate jurisdiction blocks conviction and cannot be approved", flush=True)


def main():
    global BASE
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-lifecycle", action="store_true")
    parser.add_argument("--base-url", default=BASE)
    args = parser.parse_args()
    BASE = args.base_url.rstrip("/")
    wait_ready()
    if args.with_lifecycle:
        gate_session = request("POST", "/v1/auth/register", expected=201, payload={
            "username": "ci_gate_" + uuid.uuid4().hex[:12],
            "password": secrets.token_urlsafe(24), "displayName": "CI capability gate",
        })
        gate_case = request("POST", "/v1/cases", token=gate_session["token"], expected=201,
                            payload={"title": "CI capability gate", "jurisdiction": "CI"})
        request("POST", f"/v2/cases/{gate_case['id']}/modules/compliance/executions",
                token=gate_session["token"], expected=501)
        seed_path = Path(__file__).resolve().with_name("ci_seed_registry.py")
        subprocess.run([
            "docker", "compose", "exec", "-T", "-e", "LEXCYBER_CI_FIXTURES=1",
            "engine", "python", "-",
        ], input=seed_path.read_bytes(), check=True,
            cwd=seed_path.parent.parent)
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
    if args.with_lifecycle:
        lifecycle_session = request("POST", "/v1/auth/register", expected=201, payload={
            "username": "ci_lifecycle_" + uuid.uuid4().hex[:12],
            "password": secrets.token_urlsafe(24), "displayName": "CI lifecycle fixture",
        })
        run_lifecycle(lifecycle_session["token"])


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, RuntimeError, urllib.error.URLError, TimeoutError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
