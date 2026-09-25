from datetime import datetime, timezone
from typing import Any

from retrieval.gateway import RetrievalGateway
from retrieval.schemas import RetrievalQuery
from skills.shared import warning_list


def execute(payload: dict[str, Any]) -> dict[str, Any]:
    response = RetrievalGateway().search(
        RetrievalQuery(query=payload["query"], top_k=payload.get("top_k", 5), filters=payload.get("filters", {}))
    )
    retrieved_at = datetime.now(timezone.utc).isoformat()
    documents = []
    citations = []
    for document in response.documents:
        item = document.model_dump()
        metadata = item.get("metadata") or {}
        citation = {
            "source_id": item.get("id"),
            "source_version": metadata.get("source_version"),
            "title": metadata.get("title"),
            "article": metadata.get("article"),
            "jurisdiction": metadata.get("jurisdiction") or payload.get("jurisdiction"),
            "effective_from": metadata.get("effective_from"),
            "effective_to": metadata.get("effective_to"),
            "quote": item.get("content", "")[:240],
            "retrieved_at": retrieved_at,
        }
        item["citation"] = citation
        documents.append(item)
        citations.append(citation)
    return {
        "documents": documents,
        "citations": citations,
        "warnings": warning_list() if documents else ["no private knowledge-base result was returned"],
    }
