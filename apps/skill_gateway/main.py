from fastapi import FastAPI, HTTPException

from skill_runtime.executor import SkillExecutor
from skill_runtime.schemas import SkillRequest


app = FastAPI(title="Lex Skill Gateway", version="0.1.0")
executor = SkillExecutor()


@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": "lex-skill-gateway"}


@app.get("/v1/skills")
def list_skills():
    return {"skills": executor.list_skills()}


@app.post("/v1/skills/execute")
def execute_skill(request: SkillRequest):
    result = executor.execute(request)
    if result.status == "failed":
        raise HTTPException(status_code=422, detail=result.model_dump())
    return result
