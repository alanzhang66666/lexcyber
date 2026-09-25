import httpx

from config.settings import settings
from retrieval.gateway import RetrievalGateway
from retrieval.schemas import RetrievalQuery, RetrievalResponse
from skill_runtime.executor import SkillExecutor
from skill_runtime.schemas import SkillRequest


class ToolGateway:
    """Single boundary for retrieval, file, database and future MCP tools."""

    def __init__(self):
        self.local_retrieval = RetrievalGateway()
        self.skill_executor = SkillExecutor()

    def call(self, tool_name: str, arguments: dict):
        if tool_name == "skill.list":
            return {"skills": self.skill_executor.list_skills()}
        if tool_name == "skill.execute":
            return self.skill_executor.execute(SkillRequest.model_validate(arguments)).model_dump()
        if tool_name != "retrieval.search":
            raise ValueError(f"tool is not registered: {tool_name}")
        query = RetrievalQuery.model_validate(arguments)
        if settings.retrieval_gateway_url:
            try:
                with httpx.Client(timeout=20) as client:
                    response = client.post(f"{settings.retrieval_gateway_url.rstrip('/')}/retrieval/search", json=query.model_dump())
                    response.raise_for_status()
                    return RetrievalResponse.model_validate(response.json())
            except httpx.HTTPError:
                pass
        return self.local_retrieval.search(query)
