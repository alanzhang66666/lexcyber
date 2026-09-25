from __future__ import annotations

import json
import re
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from engine.settings import settings


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


@lru_cache(maxsize=1)
def _sources() -> tuple[dict[str, Any], ...]:
    path = Path(settings.knowledge_root) / "sources" / "legal_sources.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return tuple(dict(item) for item in payload.get("sources", []))


def _effective_status(source: dict[str, Any], as_of: date) -> str:
    start = _parse_date(source.get("effective_from"))
    end = _parse_date(source.get("effective_to"))
    if start is None:
        return "date_unknown"
    if as_of < start:
        return "not_yet_effective"
    if end and as_of > end:
        return "expired"
    return "effective"


def search_knowledge(query: str, *, as_of_date: str | None = None, top_k: int = 5) -> dict[str, Any]:
    normalized = re.sub(r"\s+", "", str(query or "")).lower()
    tokens = [item for item in re.split(r"[\s,，。、《》第条款项目（）()；;：:]+", normalized) if len(item) >= 2]
    checked = _parse_date(as_of_date) or date.today()
    scored: list[tuple[float, dict[str, Any]]] = []
    for source in _sources():
        haystack = re.sub(
            r"\s+",
            "",
            " ".join(
                [
                    str(source.get("title", "")),
                    str(source.get("document_number", "")),
                    str(source.get("article", "")),
                    str(source.get("excerpt", "")),
                    " ".join(str(item) for item in source.get("aliases", [])),
                ]
            ),
        ).lower()
        score = 0.0
        if normalized and normalized in haystack:
            score = 1.0
        hits = sum(token in haystack for token in tokens)
        if hits:
            score = max(score, min(0.95, 0.25 + hits * 0.12))
        if score <= 0:
            continue
        item = dict(source)
        item["effective_status"] = _effective_status(source, checked)
        item["checked_as_of"] = checked.isoformat()
        item["score"] = round(score, 4)
        item["content"] = str(source.get("excerpt") or "")
        scored.append((score, item))
    scored.sort(key=lambda pair: (-pair[0], str(pair[1].get("id"))))
    documents = [item for _, item in scored[: max(1, min(int(top_k), 20))]]
    warnings = []
    if not documents:
        warnings.append("query is outside the bundled legal-source coverage")
    if any(item.get("effective_status") != "effective" for item in documents):
        warnings.append("one or more matched sources are not effective on the requested date")
    warnings.append("bundled legal sources are limited to the reviewed demonstration corpus")
    return {
        "query": query,
        "as_of_date": checked.isoformat(),
        "coverage": "lexcyber-competition-legal-demo",
        "documents": documents,
        "warnings": warnings,
    }
