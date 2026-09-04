from pydantic import BaseModel


class ReviewDecision(BaseModel):
    actor: str | None = None
    comment: str | None = None
