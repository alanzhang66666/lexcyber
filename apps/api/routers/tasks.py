from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from apps.worker.tasks import process_task
from storage.postgres.repository import create_task, get_task

router = APIRouter()


class TaskCreate(BaseModel):
    query: str = Field(min_length=1)
    session_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.post("/v1/tasks", status_code=202)
def submit_task(payload: TaskCreate):
    task = create_task(payload.query, payload.session_id, payload.metadata)
    process_task.send(task["id"])
    return task


@router.get("/v1/tasks/{task_id}")
def task_status(task_id: str):
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    return task
