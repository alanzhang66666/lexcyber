from typing import Any, Literal

from pydantic import BaseModel, Field


class SkillManifest(BaseModel):
    id: str
    name: str
    version: str
    kind: Literal["python", "connector", "prompt", "workflow"] = "python"
    description: str
    entrypoint: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    permissions: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int = 30
    risk_level: Literal["low", "medium", "high"] = "low"
    enabled: bool = True


class SkillRequest(BaseModel):
    skill_id: str
    skill_version: str | None = None
    input: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SkillResult(BaseModel):
    skill_id: str
    skill_version: str
    status: Literal["completed", "failed"]
    output: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    duration_ms: int = 0
    error: str | None = None
