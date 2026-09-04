from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from apps.worker.tasks import process_task
from domain.cases.repository import create_matter, load_matter
from storage.postgres.repository import create_task

router = APIRouter()


class CaseCreate(BaseModel):
    title: str = Field(min_length=1)
    jurisdiction: str | None = "CN"
    as_of_date: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CaseTaskCreate(BaseModel):
    query: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.post("/v1/cases")
def create_case(payload: CaseCreate):
    try:
        return create_matter(payload.title, payload.jurisdiction, payload.as_of_date, payload.metadata)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"case store unavailable: {exc}") from exc


@router.get("/v1/cases/{case_id}")
def get_case(case_id: str):
    try:
        case = load_matter(case_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not case:
        raise HTTPException(status_code=404, detail="case not found")
    return case


@router.post("/v1/cases/{case_id}/tasks", status_code=202)
def create_case_task(case_id: str, payload: CaseTaskCreate):
    metadata = dict(payload.metadata)
    metadata["case_id"] = case_id
    try:
        task = create_task(payload.query, None, metadata)
        process_task.send(task["id"])
        return task
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/v1/cases/{case_id}/tasks")
def list_case_tasks(case_id: str):
    return {"case_id": case_id, "tasks": []}
