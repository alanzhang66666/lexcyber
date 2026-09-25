from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

SkillStatus = Literal["pending", "running", "completed", "failed", "timeout", "denied", "need_human"]
RiskLevel = Literal["low", "medium", "high", "prohibited"]
SkillKind = Literal["python", "connector", "prompt", "workflow"]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SkillManifest(BaseModel):
    id: str
    name: str
    version: str
    pack: str = "legal"
    category: str = "general"
    kind: SkillKind = "python"
    description: str
    handler: str | None = None
    entrypoint: str | None = None
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    permissions: list[str] | dict[str, str] = Field(default_factory=list)
    timeout_seconds: int = 30
    risk_level: RiskLevel = "low"
    enabled: bool = True
    status: Literal["active", "disabled", "deprecated"] = "active"

    @model_validator(mode="after")
    def require_handler(self) -> "SkillManifest":
        if not (self.handler or self.entrypoint):
            raise ValueError("skill manifest requires handler or entrypoint")
        return self

    @property
    def callable_path(self) -> str:
        path = self.handler or self.entrypoint
        assert path is not None
        return path

    def permission_list(self) -> list[str]:
        if isinstance(self.permissions, list):
            return [item for item in self.permissions if item]
        result: list[str] = []
        network = str(self.permissions.get("network", "none"))
        storage = str(self.permissions.get("object_storage", "none"))
        if network not in {"", "none"}:
            result.append("network:access")
            if "retrieval" in network:
                result.append("legal_source:search")
        if storage not in {"", "none"}:
            result.append("document:read")
        return result


class SkillRequest(BaseModel):
    skill_id: str
    skill_version: str | None = None
    input: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    actor: str = "system"
    case_id: str | None = None
    request_id: str | None = None
    parent_execution_id: str | None = None
    granted_permissions: list[str] | None = None
    human_approved: bool = False
    idempotency_key: str | None = None

    def context(self) -> dict[str, Any]:
        merged = dict(self.metadata)
        if self.case_id:
            merged.setdefault("case_id", self.case_id)
        if self.request_id:
            merged.setdefault("request_id", self.request_id)
        return merged


class SkillCitation(BaseModel):
    source_id: str | None = None
    source_version: str | None = None
    title: str | None = None
    article: str | None = None
    jurisdiction: str | None = None
    effective_from: str | None = None
    effective_to: str | None = None
    document_id: str | None = None
    page: int | None = None
    quote: str | None = None
    retrieved_at: str | None = None


class SkillResult(BaseModel):
    execution_id: str = Field(default_factory=lambda: str(uuid4()))
    skill_id: str
    skill_version: str
    status: SkillStatus
    output: dict[str, Any] = Field(default_factory=dict)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None
    error_code: str | None = None
    permission_result: str | None = None
    input_hash: str | None = None
    output_hash: str | None = None
    source_ids: list[str] = Field(default_factory=list)
    actor: str = "system"
    case_id: str | None = None
    request_id: str | None = None
    human_approval: bool = False
    model_usage: dict[str, Any] = Field(default_factory=dict)
    started_at: str = Field(default_factory=lambda: utcnow().isoformat())
    finished_at: str | None = None
    duration_ms: int = 0

    def mark_finished(self) -> "SkillResult":
        self.finished_at = utcnow().isoformat()
        return self
