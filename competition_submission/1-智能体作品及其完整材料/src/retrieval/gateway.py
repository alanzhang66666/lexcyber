import httpx

from config.settings import settings
from retrieval.corpus import search_corpus
from retrieval.schemas import RetrievalQuery, RetrievalResponse


class RetrievalGateway:
    """Stable retrieval contract for the existing private knowledge base."""

    def search(self, query: RetrievalQuery) -> RetrievalResponse:
        if settings.knowledge_base_url:
            with httpx.Client(timeout=20) as client:
                result = client.post(f"{settings.knowledge_base_url.rstrip('/')}/retrieval/search", json=query.model_dump())
                result.raise_for_status()
                return RetrievalResponse.model_validate(result.json())
        documents = search_corpus(query.query, query.top_k)
        jurisdiction = (query.filters or {}).get("jurisdiction")
        if jurisdiction:
            documents = [item for item in documents if (item.metadata or {}).get("jurisdiction") == jurisdiction]
        return RetrievalResponse(documents=documents)
