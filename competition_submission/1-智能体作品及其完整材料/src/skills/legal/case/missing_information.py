from typing import Any

from skills.legal.case.fact_extract import execute as extract_facts
from skills.legal.case.party_extract import execute as extract_parties
from skills.shared import warning_list

REQUIRED = ("parties", "dates", "claims", "jurisdiction")


def execute(payload: dict[str, Any]) -> dict[str, Any]:
    text = payload.get("text") or ""
    case = payload.get("case") or {}
    parties = case.get("parties") or extract_parties({"text": text}).get("parties", [])
    facts = case.get("facts") or extract_facts({"text": text}).get("facts", [])
    claims = case.get("claims") or payload.get("claims") or []
    present = {
        "parties": bool(parties),
        "dates": any(item.get("type") == "date" for item in facts),
        "claims": bool(claims),
        "jurisdiction": bool(payload.get("jurisdiction") or case.get("jurisdiction")),
    }
    missing = [name for name in REQUIRED if not present[name]]
    return {
        "missing": missing,
        "present": present,
        "complete": not missing,
        "warnings": warning_list(*[f"missing {item}" for item in missing]),
    }
