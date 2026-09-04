import re
from datetime import datetime
from typing import Any

from skills.legal.case.fact_extract import execute as extract_facts
from skills.shared import warning_list


def _sort_key(event: dict[str, Any]) -> tuple[int, str]:
    value = str(event.get("date", ""))
    normalized = re.sub(r"[年月]", "-", value).replace("日", "").replace("/", "-")
    try:
        return (0, datetime.strptime(normalized, "%Y-%m-%d").isoformat())
    except ValueError:
        return (1, value)


def execute(payload: dict[str, Any]) -> dict[str, Any]:
    events = list(payload.get("events", []))
    if not events and payload.get("text"):
        facts = extract_facts({"text": payload["text"], "document_id": payload.get("document_id")})["facts"]
        events = [
            {
                "date": fact["value"],
                "description": "date detected in source text",
                "confidence": fact.get("confidence", 0.6),
                "source": fact.get("source"),
                "document_id": payload.get("document_id"),
            }
            for fact in facts
            if fact["type"] == "date"
        ]
    ordered = sorted(events, key=_sort_key)
    return {"events": ordered, "warnings": warning_list() if ordered else ["no events supplied"]}
