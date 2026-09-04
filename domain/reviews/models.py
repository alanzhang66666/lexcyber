from typing import Any

from pydantic import BaseModel, Field


class ReviewRequest(BaseModel):
    id: str | None = None
    case_id: str | None = None
    task_id: str | None = None
    status: str = "pending"
    risk_level: str | None = None
    reason: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
