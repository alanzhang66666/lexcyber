from uuid import uuid4

import pytest

from engine.adapters.sentencing import SentencingUnavailable
from engine.model_probe import ModelProbeRunner
from engine.worker import run_execution
from engine.workflow import DispatchingWorkflowRunner, StubWorkflowRunner
from models.errors import ModelFailedError, ModelTimeoutError
from models.schemas import ModelResponse


class FakeGateway:
    def __init__(self, response: ModelResponse | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error

    def invoke(self, request, fallback: bool = True):
        assert fallback is False
        assert request.task_type == "model.probe"
        if self.error:
            raise self.error
        return self.response


def test_probe_runner_wraps_gateway_metadata() -> None:
    gateway = FakeGateway(ModelResponse(
        content="pong", model="stub-general-v1", provider="stub",
        token_usage={"prompt_tokens": 3}, latency_ms=12,
    ))
    result = ModelProbeRunner(gateway).run({"metadata": {"taskType": "model.probe"}})
    assert result["schemaVersion"] == "model.probe.v1"
    assert result["taskType"] == "model.probe"
    assert result["provider"] == "stub"
    assert result["echo"] == "pong"
    assert result["latencyMs"] == 12


def test_dispatch_routes_probe_and_sentencing() -> None:
    runner = DispatchingWorkflowRunner(
        StubWorkflowRunner(),
        probe_runner=ModelProbeRunner(FakeGateway(ModelResponse(content="pong", model="m", provider="openai"))),
    )
    probed = runner.run({"query": "probe", "metadata": {"taskType": "model.probe"}})
    assert probed["schemaVersion"] == "model.probe.v1"
    with pytest.raises(SentencingUnavailable):
        runner.run({"query": "calc", "metadata": {"taskType": "sentencing.calculate"}})


def test_worker_maps_model_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, object] = {}
    monkeypatch.setattr("engine.worker.mark_running", lambda execution_id, owner, stage="running": recorded.update(stage=stage) or True)
    monkeypatch.setattr(
        "engine.worker.build_runner",
        lambda: type("R", (), {"run": staticmethod(lambda payload: (_ for _ in ()).throw(ModelTimeoutError("timed out")))})(),
    )

    def complete(execution_id, status, stage, fencing_token, result=None, error_code=None,
                 error_message=None, retryable=False, owner="", human_review_required=False):
        recorded.update(status=status, error_code=error_code, complete_stage=stage)
        return True

    monkeypatch.setattr("engine.worker.complete_execution", complete)
    monkeypatch.setattr("engine.worker._notify_application", lambda execution_id: None)
    with pytest.raises(ModelTimeoutError):
        run_execution({"execution_id": str(uuid4()), "metadata": {"taskType": "model.probe"}})
    assert recorded["stage"] == "model_probe"
    assert recorded["status"] == "failed"
    assert recorded["error_code"] == "MODEL_TIMEOUT"


def test_worker_maps_model_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, object] = {}
    monkeypatch.setattr("engine.worker.mark_running", lambda execution_id, owner, stage="running": True)
    monkeypatch.setattr(
        "engine.worker.build_runner",
        lambda: type("R", (), {"run": staticmethod(lambda payload: (_ for _ in ()).throw(ModelFailedError("bad")))})(),
    )

    def complete(execution_id, status, stage, fencing_token, result=None, error_code=None,
                 error_message=None, retryable=False, owner="", human_review_required=False):
        recorded.update(status=status, error_code=error_code)
        return True

    monkeypatch.setattr("engine.worker.complete_execution", complete)
    monkeypatch.setattr("engine.worker._notify_application", lambda execution_id: None)
    with pytest.raises(ModelFailedError):
        run_execution({"execution_id": str(uuid4()), "metadata": {"taskType": "model.probe"}})
    assert recorded["error_code"] == "MODEL_FAILED"
