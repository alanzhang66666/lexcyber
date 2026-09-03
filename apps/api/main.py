from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from apps.worker.tasks import process_task
from storage.postgres.repository import create_task, get_task, init_db
from storage.redis import configure_broker


class TaskCreate(BaseModel):
    query: str = Field(min_length=1)
    session_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    configure_broker()
    yield


app = FastAPI(title="Lex Multi-Agent Backend", version="0.1.0", lifespan=lifespan)


@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": "lex-api"}


@app.post("/v1/tasks", status_code=202)
def submit_task(payload: TaskCreate):
    task = create_task(payload.query, payload.session_id, payload.metadata)
    process_task.send(task["id"])
    return task


@app.get("/v1/tasks/{task_id}")
def task_status(task_id: str):
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    return task
