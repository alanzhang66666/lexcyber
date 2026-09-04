from fastapi import APIRouter, HTTPException

from skill_runtime.executor import SkillExecutor
from skill_runtime.schemas import SkillRequest
from storage.postgres.skill_store import get_skill_execution

router = APIRouter()
executor = SkillExecutor()


@router.get("/v1/skills")
def list_skills():
    return {"skills": executor.list_skills()}


@router.get("/v1/skills/{skill_id}")
def get_skill(skill_id: str):
    matches = [item for item in executor.list_skills() if item["id"] == skill_id]
    if not matches:
        raise HTTPException(status_code=404, detail="skill not found")
    return matches[0]


@router.post("/v1/skills/{skill_id}/execute")
def execute_skill(skill_id: str, request: SkillRequest):
    request.skill_id = skill_id
    result = executor.execute(request)
    if result.error_code == "SKILL_NOT_FOUND":
        raise HTTPException(status_code=404, detail=result.model_dump())
    return result


@router.get("/v1/skill-executions/{execution_id}")
def skill_execution(execution_id: str):
    try:
        record = get_skill_execution(execution_id)
    except Exception:
        record = None
    if not record:
        raise HTTPException(status_code=404, detail="execution not found")
    return record
