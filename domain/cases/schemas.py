from pydantic import BaseModel, Field


class CaseCreate(BaseModel):
    title: str
    jurisdiction: str | None = "CN"
    as_of_date: str | None = None
    metadata: dict = Field(default_factory=dict)
