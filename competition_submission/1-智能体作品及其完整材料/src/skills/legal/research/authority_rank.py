from typing import Any

AUTHORITY_RANK = {
    "constitution": 100,
    "law": 90,
    "judicial_interpretation": 80,
    "administrative_regulation": 70,
    "local_regulation": 60,
    "department_rule": 50,
    "case": 40,
    "secondary": 10,
}


def execute(payload: dict[str, Any]) -> dict[str, Any]:
    sources = list(payload.get("sources") or payload.get("documents") or [])
    ranked = []
    for source in sources:
        metadata = source.get("metadata") or source
        authority = str(metadata.get("source_authority") or metadata.get("authority") or "secondary")
        ranked.append(
            {
                **source,
                "source_authority": authority,
                "authority_score": AUTHORITY_RANK.get(authority, 0),
                "jurisdiction": metadata.get("jurisdiction") or payload.get("jurisdiction"),
                "title": metadata.get("title") or source.get("title"),
            }
        )
    ranked.sort(key=lambda item: item.get("authority_score", 0), reverse=True)
    return {"sources": ranked, "warnings": [] if ranked else ["no sources supplied"]}
