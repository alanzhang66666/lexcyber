from __future__ import annotations

import secrets
from uuid import UUID

import dramatiq
from fastapi import Depends, FastAPI, Header, HTTPException, status

from engine.adapters.sources import search_legal_sources
from engine.contracts import ExecutionRequest, ExecutionView, SourceSearchRequest, canonical_input_hash
from engine.settings import settings
from engine.store import claim_enqueue, create_execution, get_execution, mark_enqueued, release_enqueue

app = FastAPI(title="LexCyber Execution Engine", version="0.3.0")


def require_service_token(x_service_token: str = Header(default="")) -> None:
    if not settings.service_token or not secrets.compare_digest(x_service_token, settings.service_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid service token")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "lexcyber-engine", "version": "0.3.0"}


@app.post("/internal/v1/executions", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_service_token)])
def submit_execution(payload: ExecutionRequest) -> ExecutionView:
    if payload.input_hash != canonical_input_hash(payload.query, payload.case_id, payload.session_id, payload.metadata):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="input hash does not match execution input")
    try:
        view = create_execution(payload.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=503, detail="engine persistence unavailable") from exc
    if (
        str(view.get("task_id")) != str(payload.task_id)
        or view.get("input_hash") != payload.input_hash
        or str(view.get("result_id")) != str(payload.result_id)
        or view.get("result_version") != payload.result_version
        or view.get("result_type") != payload.result_type
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="execution id is already bound to a different request")
    try:
        if claim_enqueue(payload.execution_id):
            execute_task.send(payload.model_dump(mode="json"))
            mark_enqueued(payload.execution_id)
    except Exception as exc:
        release_enqueue(payload.execution_id, str(exc))
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="engine queue unavailable") from exc
    return ExecutionView.model_validate(view)


@app.get("/internal/v1/executions/{execution_id}", dependencies=[Depends(require_service_token)])
def execution_status(execution_id: UUID) -> ExecutionView:
    try:
        view = get_execution(execution_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="engine persistence unavailable") from exc
    if not view:
        raise HTTPException(status_code=404, detail="execution not found")
    return ExecutionView.model_validate(view)


@app.post("/internal/v1/sources/search", dependencies=[Depends(require_service_token)])
def source_search(payload: SourceSearchRequest) -> dict:
    return search_legal_sources(
        payload.query,
        as_of_date=payload.as_of_date,
        source_ids=payload.source_ids,
        jurisdiction=payload.jurisdiction,
        top_k=payload.top_k,
    )


@dramatiq.actor(max_retries=2, time_limit=300_000)
def execute_task(payload: dict) -> None:
    from engine.worker import run_execution

    run_execution(payload)
