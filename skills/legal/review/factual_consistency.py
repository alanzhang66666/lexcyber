from collections import defaultdict
from typing import Any


def execute(payload: dict[str, Any]) -> dict[str, Any]:
    facts = list(payload.get("facts") or [])
    grouped: dict[str, set[str]] = defaultdict(set)
    for fact in facts:
        grouped[str(fact.get("type") or "fact")].add(str(fact.get("value")))
    issues = []
    for fact_type, values in grouped.items():
        if fact_type in {"amount", "date"} and len(values) > 1:
            issues.append({"type": "conflict", "field": fact_type, "values": sorted(values)})
    status = "FAIL" if issues else "PASS"
    return {
        "status": status,
        "issues": issues,
        "missing_information": [],
        "unsupported_claims": [],
        "invalid_citations": [],
        "warnings": ["factual conflicts detected"] if issues else [],
    }
