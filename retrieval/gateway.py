import httpx

from config.settings import settings
from retrieval.schemas import RetrievalQuery, RetrievalResponse


class RetrievalGateway:
    """Stable retrieval contract for the existing private knowledge base."""

    def search(self, query: RetrievalQuery) -> RetrievalResponse:
        if not settings.knowledge_base_url:
            return RetrievalResponse()
        with httpx.Client(timeout=20) as client:
            result = client.post(f"{settings.knowledge_base_url.rstrip('/')}/retrieval/search", json=query.model_dump())
            result.raise_for_status()
            return RetrievalResponse.model_validate(result.json())
