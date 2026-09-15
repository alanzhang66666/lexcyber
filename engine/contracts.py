import hashlib
import json
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import AliasChoices, BaseModel, Field


def canonical_input_hash(query: str, case_id: str | None, session_id: str | None, metadata: dict[str, Any]) -> str:
    canonical = json.dumps(
        {"case_id": case_id, "metadata": metadata, "query": query, "session_id": session_id},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ExecutionRequest(BaseModel):
    """Versioned envelope persisted by Java and consumed by Engine/Worker."""

    task_id: UUID
    execution_id: UUID
    request_id: UUID
    result_id: UUID
    result_version: int = Field(ge=1)
    result_type: str = "workflow.output"
    query: str = Field(min_length=1, max_length=20_000)
    case_id: str | None = None
    session_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    input_hash: str = Field(min_length=16, max_length=128)
    contract_version: str = "public-api-0.3"


class ExecutionView(BaseModel):
    execution_id: UUID
    task_id: UUID
    request_id: UUID
    status: str
    current_stage: str
    result_id: UUID | None = None
    result_version: int | None = None
    result_type: str | None = None
    content_json: str | None = None
    content_hash: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False
    result_ref: dict[str, Any] | None = None
    updated_at: datetime | None = None
    input_hash: str | None = None
    enqueued_at: datetime | None = None


class SourceSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2_000)
    as_of_date: str | None = Field(default=None, validation_alias=AliasChoices("as_of_date", "asOfDate"))
    source_ids: list[str] = Field(default_factory=list, validation_alias=AliasChoices("source_ids", "sourceIds"))
    jurisdiction: str = "CN"
    top_k: int = Field(default=5, ge=1, le=20, validation_alias=AliasChoices("top_k", "topK"))
