from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ExecutionRequest(BaseModel):
    task_id: UUID
    execution_id: UUID
    request_id: UUID
    query: str = Field(min_length=1, max_length=20_000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    input_hash: str = Field(min_length=16)
    contract_version: str = "public-api-0.3"


class ExecutionView(BaseModel):
    execution_id: UUID
    task_id: UUID
    status: str
    current_stage: str
    error_code: str | None = None
    result_ref: dict[str, Any] | None = None
    updated_at: datetime | None = None
