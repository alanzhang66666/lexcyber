from uuid import uuid4

import pytest

from engine.document_parse import (
    DocumentParseError,
    DocumentParseRunner,
    wrap_parse_result,
)
from engine.worker import run_execution
from engine.workflow import DispatchingWorkflowRunner, StubWorkflowRunner, build_runner
from skill_runtime.errors import SkillTimeoutError


def test_wrap_parse_result_adds_locators_and_keeps_full_structures() -> None:
    content = wrap_parse_result(
        {
            "text": "测试案例 001\n以下为开发样例正文。",
            "paragraphs": [{"paragraph": 1, "text": "测试案例 001", "style": "Title"}],
            "tables": [{"table": 1, "rows": [["项目", "内容"]]}],
            "pages": [{"page": 1, "text": "ignored for docx"}],
            "warnings": [],
        },
        document_id="doc-demo-001",
        fmt="docx",
    )
    assert content["schemaVersion"] == "document.parse.v1"
    assert content["taskType"] == "document.parse"
    assert content["pages"] == []
    assert content["paragraphs"][0]["locator"] == "paragraph:1"
    assert content["tables"][0]["locator"] == "table:1"
    assert content["text"].startswith("测试案例 001")


def test_pdf_pages_get_locators_and_empty_paragraphs() -> None:
    content = wrap_parse_result(
        {"text": "page text", "pages": [{"page": 1, "text": "page text", "width": 595.0, "height": 842.0}], "warnings": []},
        document_id="doc-demo-002",
        fmt="pdf",
    )
    assert content["pages"][0]["locator"] == "page:1"
    assert content["paragraphs"] == []
    assert content["tables"] == []


def test_document_parse_runner_reads_stored_bytes_not_empty_text() -> None:
    seen: dict[str, object] = {}

    def parse_docx(payload: dict) -> dict:
        seen["payload"] = payload
        return {"paragraphs": [{"paragraph": 1, "text": "正文", "style": "Normal"}], "tables": [], "text": "正文", "warnings": []}

    runner = DocumentParseRunner(fetch_bytes=lambda key: b"real-docx-bytes", parse_docx_fn=parse_docx, timeout_seconds=5)
    result = runner.run({
        "query": "parse",
        "metadata": {
            "taskType": "document.parse",
            "documentId": "doc-demo-001",
            "storageKey": "cases/case-1/doc-demo-001/abc",
            "filename": "案情材料.docx",
            "contentType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        },
    })
    assert result["documentId"] == "doc-demo-001"
    assert result["format"] == "docx"
    assert "content_base64" in seen["payload"]
    assert seen["payload"]["content_base64"]


def test_fatal_parse_warning_is_document_parse_failed() -> None:
    runner = DocumentParseRunner(
        fetch_bytes=lambda key: b"bad-bytes",
        parse_docx_fn=lambda payload: {"paragraphs": [], "tables": [], "text": "", "warnings": ["docx parse failed: damaged"]},
        timeout_seconds=5,
    )
    with pytest.raises(DocumentParseError, match="无法解析该文件") as error:
        runner.run({"metadata": {"taskType": "document.parse", "storageKey": "k", "filename": "a.docx"}})
    assert error.value.code == "DOCUMENT_PARSE_FAILED"


def test_empty_stored_file_is_not_parse_success() -> None:
    runner = DocumentParseRunner(fetch_bytes=lambda key: b"", parse_docx_fn=lambda payload: {"text": "should not run"}, timeout_seconds=5)
    with pytest.raises(DocumentParseError, match="empty"):
        runner.run({"metadata": {"taskType": "document.parse", "storageKey": "k", "filename": "a.docx"}})


def test_timeout_surfaces_as_skill_timeout() -> None:
    def boom(_payload: dict) -> dict:
        raise SkillTimeoutError("skill exceeded timeout of 1s")

    runner = DocumentParseRunner(fetch_bytes=lambda key: b"bytes", parse_docx_fn=boom, timeout_seconds=5)
    with pytest.raises(SkillTimeoutError):
        runner.run({"metadata": {"taskType": "document.parse", "storageKey": "k", "filename": "a.docx"}})


def test_dispatch_uses_parse_runner_only_for_document_parse() -> None:
    parse = DocumentParseRunner(
        fetch_bytes=lambda key: b"bytes",
        parse_docx_fn=lambda payload: {"paragraphs": [{"paragraph": 1, "text": "x", "style": None}], "tables": [], "text": "x", "warnings": []},
        timeout_seconds=5,
    )
    runner = DispatchingWorkflowRunner(StubWorkflowRunner(), parse_runner=parse)
    parsed = runner.run({"query": "解析", "metadata": {"taskType": "document.parse", "storageKey": "k", "filename": "a.docx"}})
    stub = runner.run({"query": "generic", "metadata": {"source": "ci"}})
    assert parsed["schemaVersion"] == "document.parse.v1"
    assert stub["runner"] == "stub"
    assert build_runner().__class__.__name__ == "DispatchingWorkflowRunner"


def test_worker_maps_parse_failure_error_code(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, object] = {}

    monkeypatch.setattr("engine.worker.mark_running", lambda execution_id, owner, stage="running": recorded.update(stage=stage) or True)
    monkeypatch.setattr("engine.worker.build_runner", lambda: type("R", (), {"run": staticmethod(lambda payload: (_ for _ in ()).throw(DocumentParseError("无法解析该文件")))})())

    def complete(execution_id, status, stage, result=None, error_code=None, error_message=None, retryable=False):
        recorded.update(status=status, complete_stage=stage, error_code=error_code)

    monkeypatch.setattr("engine.worker.complete_execution", complete)
    monkeypatch.setattr("engine.worker._notify_application", lambda execution_id: None)

    with pytest.raises(DocumentParseError):
        run_execution({
            "execution_id": str(uuid4()),
            "metadata": {"taskType": "document.parse"},
        })
    assert recorded["stage"] == "document_parsing"
    assert recorded["status"] == "failed"
    assert recorded["error_code"] == "DOCUMENT_PARSE_FAILED"


def test_worker_maps_parse_timeout_error_code(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, object] = {}
    monkeypatch.setattr("engine.worker.mark_running", lambda execution_id, owner, stage="running": True)
    monkeypatch.setattr("engine.worker.build_runner", lambda: type("R", (), {"run": staticmethod(lambda payload: (_ for _ in ()).throw(SkillTimeoutError("timed out")))})())

    def complete(execution_id, status, stage, result=None, error_code=None, error_message=None, retryable=False):
        recorded.update(status=status, error_code=error_code, stage=stage)

    monkeypatch.setattr("engine.worker.complete_execution", complete)
    monkeypatch.setattr("engine.worker._notify_application", lambda execution_id: None)

    with pytest.raises(SkillTimeoutError):
        run_execution({"execution_id": str(uuid4()), "metadata": {"taskType": "document.parse"}})
    assert recorded["status"] == "timed_out"
    assert recorded["error_code"] == "DOCUMENT_PARSE_TIMEOUT"
