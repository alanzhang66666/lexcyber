from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from engine.settings import settings

SOURCE_PATH = Path(__file__).with_name("legal_sources.json")


class SourceSearchUnavailable(Exception):
    code = "SOURCE_SEARCH_UNAVAILABLE"

    def __init__(self, message: str = "legal source search is not enabled before T3 legal sign-off") -> None:
        super().__init__(message)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _effective_status(source: dict[str, Any], as_of: date) -> str:
    effective_from = _parse_date(source.get("effective_from"))
    effective_to = _parse_date(source.get("effective_to"))
    if effective_from is None:
        return "date_unknown"
    if as_of < effective_from:
        return "not_yet_effective"
    if effective_to and as_of > effective_to:
        return "expired"
    return "effective"


def _load_sources() -> list[dict[str, Any]]:
    return json.loads(SOURCE_PATH.read_text(encoding="utf-8"))["sources"]


def get_legal_source(source_id: str, as_of_date: str | None = None) -> dict[str, Any]:
    as_of = _parse_date(as_of_date) or date.today()
    for source in _load_sources():
        if source["id"] == source_id:
            return {**source, "effective_status": _effective_status(source, as_of), "checked_as_of": as_of.isoformat()}
    raise KeyError(f"legal source is outside the three-case corpus: {source_id}")


def search_legal_sources(
    query: str,
    *,
    as_of_date: str | None = None,
    source_ids: list[str] | None = None,
    jurisdiction: str = "CN",
    top_k: int = 5,
) -> dict[str, Any]:
    """Search the versioned official-source corpus limited to the A/B/C demo."""

    as_of = _parse_date(as_of_date) or date.today()
    normalized_query = re.sub(r"\s+", "", query).lower()
    requested = set(source_ids or [])
    scored: list[tuple[float, dict[str, Any]]] = []
    for source in _load_sources():
        if jurisdiction and source.get("jurisdiction") != jurisdiction:
            continue
        if requested and source["id"] not in requested:
            continue
        haystack = re.sub(
            r"\s+",
            "",
            " ".join(
                [
                    source.get("title", ""),
                    source.get("document_number", ""),
                    source.get("article", ""),
                    source.get("excerpt", ""),
                    " ".join(source.get("aliases", [])),
                ]
            ),
        ).lower()
        tokens = [token for token in re.split(r"[\s,，。、《》第条款项目（）()；;：:]+", query.lower()) if len(token) >= 2]
        score = 0.0
        if source["id"] in requested:
            score = 1.0
        elif normalized_query and normalized_query in haystack:
            score = 0.95
        else:
            hits = sum(token in haystack for token in tokens)
            if hits:
                score = min(0.9, 0.35 + hits * 0.12)
        if score:
            item = {**source, "effective_status": _effective_status(source, as_of), "checked_as_of": as_of.isoformat(), "score": score}
            scored.append((score, item))
    scored.sort(key=lambda item: (-item[0], item[1]["id"]))
    documents = [item for _, item in scored[: max(1, min(top_k, 50))]]
    warnings = []
    if not documents:
        warnings.append("query is outside the curated three-case legal-source corpus")
    if any(item["effective_status"] != "effective" for item in documents):
        warnings.append("one or more matched sources are not effective on the requested date; legal temporal applicability requires human review")
    warnings.append("retrieval coverage is intentionally limited to the A/B/C demo and does not establish legal applicability")
    return {
        "status": "ok" if documents else "unsupported_query",
        "query": query,
        "as_of_date": as_of.isoformat(),
        "coverage": "three_case_demo_v1",
        "documents": documents,
        "warnings": warnings,
    }


def search(query: dict[str, Any]) -> list[dict[str, Any]]:
    """T1 internal route adapter; disabled until T3 legal-source sign-off."""

    if not settings.legal_source_search_enabled:
        raise SourceSearchUnavailable()
    result = search_legal_sources(
        str(query.get("query") or ""),
        as_of_date=query.get("as_of_date"),
        jurisdiction=str(query.get("jurisdiction") or "CN"),
        top_k=int(query.get("top_k") or 5),
    )
    return [
        {
            "source_id": item["id"],
            "locator": item.get("article") or item.get("document_number") or "document",
            "title": item.get("title"),
            "quote": item.get("excerpt"),
            "version": item.get("source_version"),
            "jurisdiction": item.get("jurisdiction"),
        }
        for item in result["documents"]
    ]
