from fastapi import FastAPI, HTTPException

from skill_runtime.executor import SkillExecutor
from skill_runtime.schemas import SkillRequest

app = FastAPI(title="Lex Skill Gateway", version="0.2.0")
executor = SkillExecutor()


@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": "lex-skill-gateway", "version": "0.2.0"}


@app.get("/v1/skills")
def list_skills():
    return {"skills": executor.list_skills()}


@app.get("/v1/skills/{skill_id}")
def get_skill(skill_id: str):
    matches = [item for item in executor.list_skills() if item["id"] == skill_id]
    if not matches:
        raise HTTPException(status_code=404, detail="skill not found")
    return matches[0]


@app.post("/v1/skills/execute")
@app.post("/v1/skills/{skill_id}/execute")
def execute_skill(request: SkillRequest, skill_id: str | None = None):
    if skill_id:
        request.skill_id = skill_id
    result = executor.execute(request)
    if result.error_code == "SKILL_NOT_FOUND":
        raise HTTPException(status_code=404, detail=result.model_dump())
    return result
