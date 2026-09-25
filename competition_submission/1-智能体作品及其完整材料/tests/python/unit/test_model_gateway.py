import httpx
import pytest

from engine.model_access import EffectiveModelSettings
from models.errors import ModelFailedError, ModelNotConfiguredError, ModelTimeoutError
from models.gateway import ModelGateway
from models.schemas import ModelRequest, ModelResponse


def model_settings(**overrides: object) -> EffectiveModelSettings:
    values = {
        "model_provider": "openai",
        "model_name": "gpt",
        "model_api_base_url": "https://example.test/v1",
        "model_api_key": "k",
        "model_timeout_seconds": 1.0,
    }
    values.update(overrides)
    return EffectiveModelSettings(**values)


def test_missing_key_is_model_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("models.gateway.effective_model_settings", lambda: model_settings(model_api_key=""))
    gateway = ModelGateway()
    monkeypatch.setattr(gateway.router, "routes", lambda task_type: [type("R", (), {"provider": "openai", "model_name": "gpt"})()])
    with pytest.raises(ModelNotConfiguredError) as error:
        gateway.invoke(ModelRequest(messages=[{"role": "user", "content": "ping"}]), fallback=False)
    assert error.value.code == "MODEL_NOT_CONFIGURED"


def test_timeout_is_model_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("models.gateway.effective_model_settings", model_settings)

    class FakeClient:
        def __init__(self, timeout: float) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            raise httpx.TimeoutException("timed out")

    monkeypatch.setattr("models.gateway.httpx.Client", FakeClient)
    gateway = ModelGateway()
    monkeypatch.setattr(gateway.router, "routes", lambda task_type: [type("R", (), {"provider": "openai", "model_name": "gpt"})()])
    with pytest.raises(ModelTimeoutError) as error:
        gateway.invoke(ModelRequest(messages=[{"role": "user", "content": "ping"}]), fallback=False)
    assert error.value.code == "MODEL_TIMEOUT"


def test_http_error_is_model_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("models.gateway.effective_model_settings", model_settings)

    request = httpx.Request("POST", "https://example.test/v1/chat/completions")
    response = httpx.Response(502, request=request)

    class FakeClient:
        def __init__(self, timeout: float) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            raise httpx.HTTPStatusError("bad", request=request, response=response)

    monkeypatch.setattr("models.gateway.httpx.Client", FakeClient)
    gateway = ModelGateway()
    monkeypatch.setattr(gateway.router, "routes", lambda task_type: [type("R", (), {"provider": "openai", "model_name": "gpt"})()])
    with pytest.raises(ModelFailedError) as error:
        gateway.invoke(ModelRequest(messages=[{"role": "user", "content": "ping"}]), fallback=False)
    assert error.value.code == "MODEL_FAILED"


def test_stub_probe_does_not_claim_real_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "models.gateway.effective_model_settings",
        lambda: model_settings(model_provider="stub", model_name="stub-general", model_api_key=""),
    )
    response = ModelGateway().invoke(ModelRequest(messages=[{"role": "user", "content": "pong"}]), fallback=False)
    assert isinstance(response, ModelResponse)
    assert response.provider == "stub"
