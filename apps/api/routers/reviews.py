from fastapi import APIRouter, HTTPException

from domain.reviews.repository import apply_decision, list_pending, load_review
from domain.reviews.schemas import ReviewDecision

router = APIRouter()


@router.get("/v1/reviews")
def list_reviews(status: str | None = "pending"):
    try:
        return {"reviews": list_pending(status)}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/v1/reviews/{review_id}")
def get_review(review_id: str):
    try:
        review = load_review(review_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not review:
        raise HTTPException(status_code=404, detail="review not found")
    return review


@router.post("/v1/reviews/{review_id}/approve")
def approve(review_id: str, payload: ReviewDecision | None = None):
    return _decide(review_id, "approve", payload)


@router.post("/v1/reviews/{review_id}/reject")
def reject(review_id: str, payload: ReviewDecision | None = None):
    return _decide(review_id, "reject", payload)


@router.post("/v1/reviews/{review_id}/request-retry")
def request_retry(review_id: str, payload: ReviewDecision | None = None):
    return _decide(review_id, "request-retry", payload)


def _decide(review_id: str, decision: str, payload: ReviewDecision | None):
    payload = payload or ReviewDecision()
    try:
        review = apply_decision(review_id, decision, payload.actor, payload.comment)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not review:
        raise HTTPException(status_code=404, detail="review not found")
    return review
