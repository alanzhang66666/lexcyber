from __future__ import annotations

from typing import Any


class SourceSearchUnavailable(Exception):
    code = "SOURCE_SEARCH_UNAVAILABLE"

    def __init__(self, message: str = "legal source search is not wired") -> None:
        super().__init__(message)


def search(query: dict[str, Any]) -> list[dict[str, Any]]:
    """Reserved for T3 search_legal_sources(). Never fall back to the sample corpus."""
    _ = query
    raise SourceSearchUnavailable()
