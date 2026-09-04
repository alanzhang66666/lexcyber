from typing import Any

from pydantic import BaseModel, Field


class DocumentFile(BaseModel):
    id: str | None = None
    case_id: str | None = None
    filename: str
    content_type: str | None = None
    sha256: str | None = None
    status: str = "uploaded"
    metadata: dict[str, Any] = Field(default_factory=dict)
