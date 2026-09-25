from typing import Any

from skills.legal.research.source_search import execute as search_sources


def execute(payload: dict[str, Any]) -> dict[str, Any]:
    citation = payload["citation"]
    search = search_sources({"query": citation, "top_k": payload.get("top_k", 5), "jurisdiction": payload.get("jurisdiction")})
    matches = []
    for document in search["documents"]:
        haystack = f"{document.get('content', '')} {document.get('metadata', {})}"
        if citation in haystack or any(str(value) and str(value) in citation for value in (document.get("metadata") or {}).values()):
            matches.append(document)
    if matches:
        status = "verified"
    elif search["documents"]:
        status = "not_exactly_matched"
    else:
        status = "unavailable"
    warnings = list(search["warnings"])
    warnings.append("retrieval match is not an authoritative authenticity check")
    return {"status": status, "matches": matches, "citations": search.get("citations", []), "warnings": warnings}
