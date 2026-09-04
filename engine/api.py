from __future__ import annotations

import secrets
from uuid import UUID

import dramatiq
from fastapi import Depends, FastAPI, Header, HTTPException, status

from engine.contracts import ExecutionRequest, ExecutionView
from engine.settings import settings
from engine.store import create_execution, get_execution

app = FastAPI(title="LexCyber Execution Engine", version="0.3.0")


def require_service_token(x_service_token: str = Header(default="")) -> None:
    if not secrets.compare_digest(x_service_token, settings.service_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid service token")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "lexcyber-engine", "version": "0.3.0"}


@app.post("/internal/v1/executions", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_service_token)])
def submit_execution(payload: ExecutionRequest) -> ExecutionView:
    try:
        view = create_execution(payload.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=503, detail="engine persistence unavailable") from exc
    execute_task.send(payload.model_dump(mode="json"))
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


@dramatiq.actor(max_retries=2, time_limit=300_000)
def execute_task(payload: dict) -> None:
    from engine.worker import run_execution

    run_execution(payload)
