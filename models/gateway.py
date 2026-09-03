import time

import httpx

from config.settings import settings
from models.router import ModelRoute, ModelRouter
from models.schemas import ModelRequest, ModelResponse


class ModelGateway:
    def __init__(self):
        self.router = ModelRouter(settings)

    def invoke(self, request: ModelRequest) -> ModelResponse:
        last_error: Exception | None = None
        for index, route in enumerate(self.router.routes(request.task_type)):
            started = time.perf_counter()
            try:
                response = self._invoke_route(route, request)
                response.latency_ms = int((time.perf_counter() - started) * 1000)
                response.fallback_used = index > 0
                return response
            except Exception as exc:
                last_error = exc
        raise RuntimeError("all model routes failed") from last_error

    def _invoke_route(self, route: ModelRoute, request: ModelRequest) -> ModelResponse:
        if route.provider == "stub":
            text = request.messages[-1]["content"] if request.messages else ""
            return ModelResponse(content=f"[stub:{route.model_name}] 通用处理结果：{text[:500]}", model=route.model_name, provider="stub", token_usage={"prompt_tokens": len(text), "completion_tokens": 0})
        if route.provider != "openai":
            raise ValueError(f"unsupported model provider: {route.provider}")
        if not settings.model_api_key:
            raise RuntimeError("MODEL_API_KEY is required for the configured model provider")
        with httpx.Client(timeout=settings.model_timeout_seconds) as client:
            result = client.post(f"{settings.model_api_base_url.rstrip('/')}/chat/completions", headers={"Authorization": f"Bearer {settings.model_api_key}"}, json={"model": route.model_name, "messages": request.messages})
            result.raise_for_status()
            payload = result.json()
        usage = payload.get("usage") or {}
        return ModelResponse(content=payload["choices"][0]["message"]["content"], model=route.model_name, provider=route.provider, token_usage={k: int(v) for k, v in usage.items() if isinstance(v, int)})
