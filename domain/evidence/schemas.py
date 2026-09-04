from pydantic import BaseModel, Field


class EvidenceCreate(BaseModel):
    name: str
    content: str | None = None
    metadata: dict = Field(default_factory=dict)
