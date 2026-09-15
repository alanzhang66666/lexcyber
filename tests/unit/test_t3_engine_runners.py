from fastapi.testclient import TestClient

from engine.api import app
from engine.runners import DocumentParseRunner, RunnerInputError, SentencingRunner
from engine.settings import settings
from engine.workflow import build_runner


def test_document_parse_runner_preserves_t1_schema_and_locators():
    payload = {
        "result_type": "document.parse.v1",
        "metadata": {
            "document": {
                "documentId": "doc-server-a",
                "filename": "material.docx",
                "text": "第一段\n第二段",
            }
        },
    }
    assert isinstance(build_runner(payload), DocumentParseRunner)
    result = build_runner(payload).run(payload)
    assert result["human_approval_required"] is False
    output = result["final_output"]
    assert output["schemaVersion"] == "document.parse.v1"
    assert output["documentId"] == "doc-server-a"
    assert [item["locator"] for item in output["paragraphs"]] == ["paragraph:1", "paragraph:2"]


def test_document_parse_runner_rejects_missing_materialized_content():
    payload = {
        "result_type": "document.parse.v1",
        "metadata": {"document": {"documentId": "doc-server-a", "filename": "material.pdf"}},
    }
    try:
        DocumentParseRunner().run(payload)
    except RunnerInputError as exc:
        assert exc.as_dict() == {
            "code": "document_parse_input_invalid",
            "path": "metadata.document",
            "message": "one of content_base64, text, or pages is required",
            "retryable": False,
        }
    else:
        raise AssertionError("missing document content must fail clearly")


def test_sentencing_runner_dispatches_three_case_block_as_waiting_review_content():
    payload = {
        "result_type": "sentencing.calculate",
        "case_id": "case-server-b",
        "metadata": {
            "sentencing": {
                "datasetCaseId": "demo-case-b-proceeds",
                "actorId": "actor-b-li",
            }
        },
    }
    assert isinstance(build_runner(payload), SentencingRunner)
    result = build_runner(payload).run(payload)
    assert result["human_approval_required"] is True
    assert result["final_output"]["caseId"] == "case-server-b"
    assert result["final_output"]["datasetCaseId"] == "demo-case-b-proceeds"
    assert result["final_output"]["analysisStatus"] == "blocked"
    assert result["final_output"]["blockers"]


def test_internal_source_search_requires_service_token_and_returns_versioned_sources(monkeypatch):
    monkeypatch.setattr(settings, "service_token", "test-service-token")
    client = TestClient(app)
    unauthorized = client.post("/internal/v1/sources/search", json={"query": "帮信"})
    assert unauthorized.status_code == 401

    response = client.post(
        "/internal/v1/sources/search",
        headers={"X-Service-Token": "test-service-token"},
        json={"query": "帮信", "asOfDate": "2026-09-14", "topK": 2},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "ok"
    assert result["as_of_date"] == "2026-09-14"
    assert 1 <= len(result["documents"]) <= 2
    assert all("effective_status" in item for item in result["documents"])
