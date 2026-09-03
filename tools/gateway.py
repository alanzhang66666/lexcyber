import httpx

from config.settings import settings
from retrieval.gateway import RetrievalGateway
from retrieval.schemas import RetrievalQuery, RetrievalResponse


class ToolGateway:
    """Single boundary for retrieval, file, database and future MCP tools."""

    def __init__(self):
        self.local_retrieval = RetrievalGateway()

    def call(self, tool_name: str, arguments: dict):
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
