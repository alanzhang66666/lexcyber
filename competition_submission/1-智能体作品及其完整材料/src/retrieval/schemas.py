from typing import Any

from pydantic import BaseModel, Field


class RetrievalQuery(BaseModel):
    query: str
    top_k: int = Field(default=5, ge=1, le=50)
    filters: dict[str, Any] = Field(default_factory=dict)


class RetrievedDocument(BaseModel):
    id: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    score: float = 0.0


class RetrievalResponse(BaseModel):
    documents: list[RetrievedDocument] = Field(default_factory=list)
