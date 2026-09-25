from __future__ import annotations

from typing import Any

from models.gateway import ModelGateway
from models.schemas import ModelRequest

PROBE_PROMPT = "Reply with the single word pong. Do not give legal advice."


class ModelProbeRunner:
    """Calls ModelGateway with a fixed non-legal prompt and records provider metadata."""

    def __init__(self, gateway: ModelGateway | None = None) -> None:
        self.gateway = gateway

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        _ = payload
        gateway = self.gateway or ModelGateway()
        response = gateway.invoke(
            ModelRequest(task_type="model.probe", messages=[{"role": "user", "content": PROBE_PROMPT}]),
            fallback=False,
        )
        return {
            "schemaVersion": "model.probe.v1",
            "taskType": "model.probe",
            "provider": response.provider,
            "model": response.model,
            "latencyMs": response.latency_ms,
            "tokenUsage": response.token_usage,
            "echo": response.content,
        }
