from pydantic import BaseModel, Field


class DocumentCreate(BaseModel):
    filename: str
    content_type: str | None = None
    metadata: dict = Field(default_factory=dict)
