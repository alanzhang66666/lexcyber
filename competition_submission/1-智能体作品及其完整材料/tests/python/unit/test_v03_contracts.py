import time
from uuid import uuid4

import pytest

from engine.contracts import ExecutionRequest, ExecutionView, canonical_input_hash
from engine.workflow import StubWorkflowRunner
from skill_runtime.errors import SkillTimeoutError
from skill_runtime.registry import SkillRegistry
from skill_runtime.timeout import run_with_timeout


def _slow_handler(payload: dict) -> dict:
    time.sleep(2)
    return payload


def test_execution_request_round_trips_all_context_fields() -> None:
    request = ExecutionRequest(
        task_id=uuid4(), execution_id=uuid4(), request_id=uuid4(), result_id=uuid4(), result_version=1,
        query="generic input", case_id="case-1", session_id="session-1", metadata={"demo": True},
        input_hash="a" * 64,
    )
    restored = ExecutionRequest.model_validate(request.model_dump(mode="json"))
    assert restored == request
    assert restored.metadata == {"demo": True}


def test_canonical_input_hash_sample_is_stable() -> None:
    assert canonical_input_hash("generic input", "case-1", "session-1", {"demo": True}) == "ef90b46dd75aff1e8410e684ba91b7a3349a1b1976c8562a566320af648c94dc"


def test_stub_runner_is_deterministic_and_review_switch_is_neutral() -> None:
    payload = {"query": "same", "metadata": {"z": 1, "a": 2}}
    first = StubWorkflowRunner().run(payload)
    second = StubWorkflowRunner().run(payload)
    assert first == second
    assert first["status"] == "PASS"
    review = StubWorkflowRunner().run({**payload, "metadata": {"demo_requires_review": True}})
    assert review["human_approval_required"] is True
    assert review["status"] == "NEED_HUMAN"


def test_core_pack_can_be_loaded_without_legal_pack() -> None:
    registry = SkillRegistry(manifests=[], packs={"core"})
    assert [item.id for item in registry.list()] == ["core.echo"]
    assert registry.get("core.echo").pack == "core"


def test_real_process_timeout_terminates_handler() -> None:
    started = time.perf_counter()
    with pytest.raises(SkillTimeoutError):
        run_with_timeout(_slow_handler, args=({"value": 1},), timeout_seconds=0.1)
    assert time.perf_counter() - started < 1.5


def test_execution_view_accepts_terminal_result_fields() -> None:
    view = ExecutionView(
        execution_id=uuid4(), task_id=uuid4(), request_id=uuid4(), status="completed", current_stage="output",
        result_id=uuid4(), result_version=1, result_type="workflow.output", content_json='{"ok":true}',
        content_hash="b" * 64, input_hash="a" * 64,
    )
    assert view.result_version == 1
