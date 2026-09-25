import time

import httpx

from engine.model_access import effective_model_settings
from models.errors import ModelError, ModelFailedError, ModelNotConfiguredError, ModelTimeoutError
from models.router import ModelRoute, ModelRouter
from models.schemas import ModelRequest, ModelResponse


class ModelGateway:
    def __init__(self):
        self.settings = effective_model_settings()
        self.router = ModelRouter(self.settings)

    def invoke(self, request: ModelRequest, fallback: bool = True) -> ModelResponse:
        routes = self.router.routes(request.task_type)
        if not fallback:
            routes = routes[:1]
        last_error: Exception | None = None
        for index, route in enumerate(routes):
            started = time.perf_counter()
            try:
                response = self._invoke_route(route, request)
                response.latency_ms = int((time.perf_counter() - started) * 1000)
                response.fallback_used = index > 0
                return response
            except ModelError as exc:
                last_error = exc
            except Exception as exc:
                last_error = exc
        if isinstance(last_error, ModelError):
            raise last_error
        raise RuntimeError("all model routes failed") from last_error

    def _invoke_route(self, route: ModelRoute, request: ModelRequest) -> ModelResponse:
        if route.provider == "stub":
            text = request.messages[-1]["content"] if request.messages else ""
            return ModelResponse(
                content=f"[stub:{route.model_name}] 通用处理结果：{text[:500]}",
                model=route.model_name,
                provider="stub",
                token_usage={"prompt_tokens": len(text), "completion_tokens": 0},
            )
        if route.provider != "openai":
            raise ModelFailedError(f"unsupported model provider: {route.provider}")
        if not self.settings.model_api_key:
            raise ModelNotConfiguredError("MODEL_API_KEY is required for the configured model provider")
        try:
            with httpx.Client(timeout=self.settings.model_timeout_seconds) as client:
                result = client.post(
                    f"{self.settings.model_api_base_url.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {self.settings.model_api_key}"},
                    json={"model": route.model_name, "messages": request.messages},
                )
                result.raise_for_status()
                payload = result.json()
        except httpx.TimeoutException as exc:
            raise ModelTimeoutError("model request timed out") from exc
        except httpx.HTTPStatusError as exc:
            raise ModelFailedError(f"model provider returned {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise ModelFailedError(str(exc)) from exc
        usage = payload.get("usage") or {}
        return ModelResponse(
            content=payload["choices"][0]["message"]["content"],
            model=route.model_name,
            provider=route.provider,
            token_usage={key: int(value) for key, value in usage.items() if isinstance(value, int)},
        )
