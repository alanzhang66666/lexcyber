from typing import Any

from skills.legal.case.party_extract import execute as extract_parties
from skills.shared import warning_list


def execute(payload: dict[str, Any]) -> dict[str, Any]:
    intake = payload.get("intake") or {}
    text = str(intake.get("text") or payload.get("text") or "")
    parties = intake.get("parties") or extract_parties({"text": text}).get("parties", [])
    case = {
        "title": intake.get("title") or (text.splitlines()[0][:80] if text.strip() else "untitled-matter"),
        "jurisdiction": payload.get("jurisdiction") or intake.get("jurisdiction") or "CN",
        "as_of_date": payload.get("as_of_date") or intake.get("as_of_date"),
        "claims": intake.get("claims") or [],
        "parties": parties,
        "source_text": text,
    }
    missing = []
    if not parties:
        missing.append("parties")
    if not case["as_of_date"]:
        missing.append("as_of_date")
    if not case["claims"]:
        missing.append("claims")
    return {"case": case, "missing": missing, "warnings": warning_list(*[f"missing {item}" for item in missing])}
