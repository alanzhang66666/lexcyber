import pytest

from skill_runtime.audit import InMemoryAuditSink
from skill_runtime.errors import (
    SkillPermissionError,
    SkillTimeoutError,
    SkillValidationError,
)
from skill_runtime.executor import SkillExecutor
from skill_runtime.policy import evaluate
from skill_runtime.registry import SkillRegistry
from skill_runtime.schemas import SkillManifest, SkillRequest
from skill_runtime.timeout import run_with_timeout
from skill_runtime.validator import validate_payload


def test_catalog_has_twenty_two_skills():
    skills = SkillExecutor().list_skills()
    ids = {skill["id"] for skill in skills}
    assert "legal.document.classify" in ids
    assert "legal.review.human_gate" in ids
    assert "document.parse.pdf" in ids
    assert len(ids) == 22
    assert all(skill["version"] == "0.2.0" for skill in skills)


def test_input_and_output_schema_validation():
    with pytest.raises(SkillValidationError):
        validate_payload({"type": "object", "required": ["text"], "properties": {"text": {"type": "string"}}}, {})
    validate_payload({"type": "object", "required": ["facts"], "properties": {"facts": {"type": "array"}}}, {"facts": []}, output=True)


def test_permission_denied():
    registry = SkillRegistry()
    manifest = registry.get("legal.source.search")
    request = SkillRequest(skill_id=manifest.id, input={"query": "民法典"}, granted_permissions=[])
    with pytest.raises(SkillPermissionError):
        evaluate(manifest, request)


def test_disabled_skill_is_rejected():
    registry = SkillRegistry()
    registry.set_status("legal.document.redact", "0.2.0", enabled=False)
    executor = SkillExecutor(registry=registry, audit_sink=InMemoryAuditSink())
    result = executor.execute(SkillRequest(skill_id="legal.document.redact", input={"text": "13812345678"}))
    assert result.status == "denied"
    assert result.error_code == "SKILL_DISABLED"


def test_timeout_is_recorded():
    with pytest.raises(SkillTimeoutError):
        run_with_timeout(lambda: __import__("time").sleep(0.5), timeout_seconds=0)


def test_executor_runs_registered_skill_and_audits():
    sink = InMemoryAuditSink()
    result = SkillExecutor(audit_sink=sink).execute(SkillRequest(skill_id="legal.citation.parse", input={"text": "依据《民法典》第五百零九条"}))
    assert result.status == "completed"
    assert result.output["citations"][0]["title"] == "民法典"
    assert result.input_hash
    assert result.output_hash
    assert sink.events[0]["skill_id"] == "legal.citation.parse"


def test_idempotency_cache():
    executor = SkillExecutor(audit_sink=InMemoryAuditSink())
    first = executor.execute(SkillRequest(skill_id="legal.document.classify", input={"text": "合同"}, idempotency_key="k1"))
    second = executor.execute(SkillRequest(skill_id="legal.document.classify", input={"text": "合同"}, idempotency_key="k1"))
    assert first.execution_id == second.execution_id


def test_handler_exception_becomes_failed_status():
    registry = SkillRegistry()
    broken = SkillManifest(
        id="legal.test.broken",
        name="broken",
        version="0.2.0",
        description="broken",
        handler="skills.legal.document.classify:missing",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    )
    registry._manifests[("legal.test.broken", "0.2.0")] = broken
    result = SkillExecutor(registry=registry, audit_sink=InMemoryAuditSink()).execute(SkillRequest(skill_id="legal.test.broken", input={}))
    assert result.status == "failed"
    assert result.error_code in {"SKILL_ENTRYPOINT_INVALID", "SKILL_HANDLER_ERROR"}
