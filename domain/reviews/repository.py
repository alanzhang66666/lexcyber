from typing import Any

from storage.postgres.domain_store import create_review, decide_review, get_review, list_reviews


def enqueue_review(case_id: str | None, task_id: str | None, risk_level: str | None, reason: str | None, payload: dict[str, Any]) -> dict[str, Any]:
    return create_review(case_id, task_id, risk_level, reason, payload)


def load_review(review_id: str) -> dict[str, Any] | None:
    return get_review(review_id)


def list_pending(status: str | None = "pending") -> list[dict[str, Any]]:
    return list_reviews(status)


def apply_decision(review_id: str, decision: str, actor: str | None = None, comment: str | None = None) -> dict[str, Any] | None:
    return decide_review(review_id, decision, actor, comment)
