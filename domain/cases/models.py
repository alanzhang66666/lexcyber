from typing import Any

from pydantic import BaseModel, Field


class Matter(BaseModel):
    id: str | None = None
    title: str
    jurisdiction: str | None = "CN"
    as_of_date: str | None = None
    status: str = "open"
    metadata: dict[str, Any] = Field(default_factory=dict)


class Party(BaseModel):
    role: str
    name: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class Fact(BaseModel):
    fact_type: str
    value: str
    source: dict[str, Any] = Field(default_factory=dict)
