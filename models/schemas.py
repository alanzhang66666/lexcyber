from typing import Any

from pydantic import BaseModel, Field


class ModelRequest(BaseModel):
    task_type: str = "general"
    messages: list[dict[str, str]]
    structured_output: dict[str, Any] | None = None
    privacy: str = "private"


class ModelResponse(BaseModel):
    content: str
    model: str
    provider: str
    token_usage: dict[str, int] = Field(default_factory=dict)
    latency_ms: int = 0
    fallback_used: bool = False
