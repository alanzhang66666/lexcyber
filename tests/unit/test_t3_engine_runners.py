from fastapi.testclient import TestClient

from engine.api import app
from engine.document_parse import DocumentParseRunner
from engine.settings import settings
from engine.workflow import DispatchingWorkflowRunner, StubWorkflowRunner, build_runner


def test_t1_document_parse_runner_preserves_schema_and_locators():
    runner = DocumentParseRunner(
        fetch_bytes=lambda _: b"stored-docx-bytes",
        parse_docx_fn=lambda _: {
            "paragraphs": [{"paragraph": 1, "text": "第一段", "style": None}],
            "tables": [],
            "text": "第一段",
            "warnings": [],
        },
    )
    payload = {
        "metadata": {
            "taskType": "document.parse",
            "documentId": "doc-server-a",
            "storageKey": "objects/hash-a",
            "filename": "material.docx",
            "contentType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }
    }
    output = runner.run(payload)
    assert output["schemaVersion"] == "document.parse.v1"
    assert output["documentId"] == "doc-server-a"
    assert output["paragraphs"][0]["locator"] == "paragraph:1"


def test_t1_dispatcher_routes_document_parse_without_a_new_public_api():
    parse_runner = DocumentParseRunner(
        fetch_bytes=lambda _: b"stored-pdf-bytes",
        parse_pdf_fn=lambda _: {"pages": [{"page": 1, "text": "第一页"}], "text": "第一页", "warnings": []},
    )
    runner = DispatchingWorkflowRunner(StubWorkflowRunner(), parse_runner=parse_runner)
    output = runner.run(
        {
            "metadata": {
                "taskType": "document.parse",
                "documentId": "doc-server-a",
                "storageKey": "objects/hash-a",
                "filename": "material.pdf",
                "contentType": "application/pdf",
            }
        }
    )
    assert output["taskType"] == "document.parse"
    assert output["pages"][0]["locator"] == "page:1"


def test_sentencing_dispatcher_preserves_blockers_for_waiting_review(monkeypatch):
    monkeypatch.setattr(settings, "sentencing_enabled", True)
    payload = {
        "case_id": "case-server-b",
        "metadata": {
            "taskType": "sentencing.calculate",
            "sentencing": {"datasetCaseId": "B", "actorId": "actor-b-huang"},
        },
    }
    result = build_runner().run(payload)
    assert result["human_approval_required"] is True
    content = result["final_output"]
    assert content["caseId"] == "case-server-b"
    assert content["datasetCaseId"] == "B"
    assert content["t3BundleId"] == "demo-case-b-proceeds"
    assert content["analysisStatus"] == "blocked"
    assert content["blockers"]


def test_internal_source_search_stays_501_until_enabled_then_returns_t1_hits(monkeypatch):
    monkeypatch.setattr(settings, "service_token", "test-service-token")
    client = TestClient(app)
    unauthorized = client.post("/internal/v1/sources/search", json={"query": "帮信"})
    assert unauthorized.status_code == 401

    disabled = client.post(
        "/internal/v1/sources/search",
        headers={"X-Service-Token": "test-service-token"},
        json={"query": "帮信", "as_of_date": "2026-09-14", "top_k": 2},
    )
    assert disabled.status_code == 501

    monkeypatch.setattr(settings, "legal_source_search_enabled", True)
    response = client.post(
        "/internal/v1/sources/search",
        headers={"X-Service-Token": "test-service-token"},
        json={"query": "帮信", "as_of_date": "2026-09-14", "top_k": 2},
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert 1 <= len(items) <= 2
    assert all({"source_id", "locator", "version"} <= set(item) for item in items)
