from typing import Any

from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    evidence_id: str
    name: str
    sha256: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
