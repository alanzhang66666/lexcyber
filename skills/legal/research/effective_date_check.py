from datetime import date
from typing import Any


def _parse(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def execute(payload: dict[str, Any]) -> dict[str, Any]:
    as_of = _parse(payload.get("as_of_date")) or date.today()
    results = []
    for source in payload.get("sources") or payload.get("documents") or []:
        metadata = source.get("metadata") or source
        effective_from = _parse(metadata.get("effective_from") or metadata.get("effective_date"))
        effective_to = _parse(metadata.get("effective_to") or metadata.get("expiry_date"))
        effective = True
        reasons = []
        if effective_from and as_of < effective_from:
            effective = False
            reasons.append("as_of_date is before effective_from")
        if effective_to and as_of > effective_to:
            effective = False
            reasons.append("as_of_date is after effective_to")
        if effective_from is None:
            reasons.append("effective_from is missing")
        results.append(
            {
                "source_id": source.get("id") or metadata.get("source_id"),
                "title": metadata.get("title") or source.get("title"),
                "effective": effective and effective_from is not None,
                "as_of_date": as_of.isoformat(),
                "effective_from": effective_from.isoformat() if effective_from else None,
                "effective_to": effective_to.isoformat() if effective_to else None,
                "reasons": reasons,
            }
        )
    return {"results": results, "warnings": [] if results else ["no sources supplied"]}
