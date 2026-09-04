import re
from typing import Any

from skills.shared import location

DATE_PATTERN = re.compile(r"(?:\d{4}[年\-/]\d{1,2}[月\-/]\d{1,2}日?|\d{4}年\d{1,2}月\d{1,2}日)")
AMOUNT_PATTERN = re.compile(r"(?:人民币|RMB|USD|\$|¥|￥)\s*[\d,]+(?:\.\d+)?\s*(?:元|dollars?)?")


def execute(payload: dict[str, Any]) -> dict[str, Any]:
    text = payload["text"]
    facts: list[dict[str, Any]] = []
    for match in DATE_PATTERN.finditer(text):
        facts.append(
            {
                "type": "date",
                "value": match.group(),
                "confidence": 0.75,
                "document_id": payload.get("document_id"),
                "source": location(start=match.start(), end=match.end()),
            }
        )
    for match in AMOUNT_PATTERN.finditer(text):
        facts.append(
            {
                "type": "amount",
                "value": match.group(),
                "confidence": 0.75,
                "document_id": payload.get("document_id"),
                "source": location(start=match.start(), end=match.end()),
            }
        )
    warning = "heuristic extraction; negation, attribution, and conflicts are not resolved"
    return {"facts": facts, "warnings": [warning] if facts else ["no supported fact pattern was detected"]}
