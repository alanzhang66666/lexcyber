from collections import defaultdict
from typing import Any


def execute(payload: dict[str, Any]) -> dict[str, Any]:
    facts = list(payload.get("facts") or [])
    statements = list(payload.get("statements") or payload.get("evidence") or [])
    values: dict[str, list[str]] = defaultdict(list)
    for item in facts + statements:
        if isinstance(item, str):
            continue
        key = str(item.get("type") or item.get("name") or "value")
        value = str(item.get("value") or item.get("content") or item.get("text") or "")
        if value:
            values[key].append(value)
    contradictions = []
    for key, observed in values.items():
        unique = list(dict.fromkeys(observed))
        if key in {"amount", "date"} and len(unique) > 1:
            contradictions.append({"field": key, "values": unique})
    return {
        "contradictions": contradictions,
        "has_conflict": bool(contradictions),
        "warnings": ["conflicting values detected"] if contradictions else [],
    }
