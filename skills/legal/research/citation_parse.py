import re
from typing import Any

from skills.shared import location, warning_list

PATTERN = re.compile(
    r"《(?P<title>[^》]{1,100})》\s*第(?P<article>(?:\d+[之-]?\d*|[零〇一二三四五六七八九十百千万两]+))条"
    r"(?:第(?P<paragraph>\d+)款)?(?:第(?P<item>[一二三四五六七八九十\d]+)项)?"
)
EN_PATTERN = re.compile(r"Article\s+(?P<article>\d+[A-Za-z-]*)\s+of\s+(?:the\s+)?(?P<title>[A-Za-z0-9][A-Za-z0-9\s]{2,80})", re.IGNORECASE)


def execute(payload: dict[str, Any]) -> dict[str, Any]:
    text = payload["text"]
    citations: list[dict[str, Any]] = []
    for match in PATTERN.finditer(text):
        citations.append(
            {
                "title": match.group("title"),
                "article": match.group("article"),
                "paragraph": match.group("paragraph"),
                "item": match.group("item"),
                "raw": match.group(),
                "jurisdiction": payload.get("jurisdiction") or "CN",
                "confidence": 0.85,
                "source": location(start=match.start(), end=match.end()),
            }
        )
    for match in EN_PATTERN.finditer(text):
        citations.append(
            {
                "title": match.group("title").strip(),
                "article": match.group("article"),
                "paragraph": None,
                "item": None,
                "raw": match.group(),
                "jurisdiction": payload.get("jurisdiction") or "US",
                "confidence": 0.7,
                "source": location(start=match.start(), end=match.end()),
            }
        )
    return {"citations": citations, "warnings": warning_list() if citations else ["no supported citation pattern was detected"]}
