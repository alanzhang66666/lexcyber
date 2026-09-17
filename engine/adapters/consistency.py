from __future__ import annotations

import re
from typing import Any

UNRESOLVED_TEMPLATE_PLACEHOLDER = re.compile(r"【[^】]+】")


def validate_result_consistency(bundle: dict[str, Any], result: dict[str, Any], draft_fields: dict[str, Any] | None = None) -> dict[str, Any]:
    """Cross-check a result/draft against the bundle's traceable ids and values."""

    issues: list[dict[str, str]] = []
    evidence_ids = {item["id"] for item in bundle.get("evidence", [])}
    source_ids = set(bundle.get("legal_source_ids", []))
    amounts = {item["id"]: item.get("value") for item in bundle.get("amounts", [])}

    for evidence_id in result.get("evidence_ids", []):
        if evidence_id not in evidence_ids:
            issues.append({"code": "unknown_evidence", "path": "result.evidence_ids", "message": evidence_id})
    for source_id in result.get("source_ids", []):
        if source_id not in source_ids:
            issues.append({"code": "unknown_legal_source", "path": "result.source_ids", "message": source_id})
    for amount_id, value in (result.get("input_snapshot") or {}).items():
        if amount_id not in amounts:
            issues.append({"code": "unknown_amount", "path": f"result.input_snapshot.{amount_id}", "message": amount_id})
        elif amounts[amount_id] != value:
            issues.append(
                {
                    "code": "amount_mismatch",
                    "path": f"result.input_snapshot.{amount_id}",
                    "message": f"bundle={amounts[amount_id]!r}, result={value!r}",
                }
            )

    required_fields = set((bundle.get("document_fields") or {}).get("required", []))
    supplied_fields = draft_fields or {}
    for field in sorted(required_fields - set(supplied_fields)):
        issues.append({"code": "draft_field_missing", "path": f"draft_fields.{field}", "message": field})
    for field, value in supplied_fields.items():
        if isinstance(value, str) and UNRESOLVED_TEMPLATE_PLACEHOLDER.search(value):
            issues.append({"code": "draft_placeholder_unresolved", "path": f"draft_fields.{field}", "message": field})

    return {
        "status": "PASS" if not issues else "NEED_HUMAN",
        "issues": issues,
        "human_review_required": True,
        "warnings": ["consistency checks do not approve legal conclusions"],
    }
