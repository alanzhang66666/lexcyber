from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any


def _decimal(value: Any, path: str, blockers: list[dict[str, str]]) -> Decimal | None:
    try:
        parsed = Decimal(str(value))
    except Exception:
        blockers.append({"code": "invalid_number", "path": path, "message": f"not a number: {value!r}"})
        return None
    if parsed < 0:
        blockers.append({"code": "negative_number", "path": path, "message": "value must not be negative"})
        return None
    return parsed


def _blocked(
    blockers: list[dict[str, str]],
    warnings: list[str] | None = None,
    *,
    case_id: str | None = None,
    actor_id: str | None = None,
) -> dict[str, Any]:
    return {
        "status": "blocked",
        "case_id": case_id,
        "actor_id": actor_id,
        "term_months": None,
        "fine": None,
        "steps": [],
        "blockers": blockers,
        "warnings": warnings or [],
        "human_review_required": True,
    }


def calculate_sentencing(payload: dict[str, Any]) -> dict[str, Any]:
    """Replay a legally approved rule with confirmed inputs; otherwise fail closed.

    This adapter is arithmetic infrastructure, not a sentencing model. It never
    chooses a rule, a base sentence, an adjustment, or an applicable source.
    """

    blockers: list[dict[str, str]] = []
    rule = payload.get("rule") or {}
    if rule.get("legal_review_status") != "approved":
        blockers.append(
            {
                "code": "rule_not_approved",
                "path": "rule.legal_review_status",
                "message": "a qualified legal reviewer must approve the exact rule version before calculation",
            }
        )
    if not rule.get("rule_version"):
        blockers.append({"code": "rule_version_missing", "path": "rule.rule_version", "message": "rule_version is required"})
    if not rule.get("source_ids"):
        blockers.append({"code": "rule_sources_missing", "path": "rule.source_ids", "message": "at least one versioned legal source is required"})

    parameters = payload.get("parameters") or []
    if not parameters:
        blockers.append({"code": "parameters_missing", "path": "parameters", "message": "confirmed calculation parameters are required"})
    snapshot: dict[str, Any] = {}
    for position, parameter in enumerate(parameters):
        path = f"parameters[{position}]"
        if parameter.get("verification_status") != "confirmed":
            blockers.append({"code": "parameter_unconfirmed", "path": f"{path}.verification_status", "message": str(parameter.get("id"))})
        if not parameter.get("evidence_ids"):
            blockers.append({"code": "parameter_source_missing", "path": f"{path}.evidence_ids", "message": str(parameter.get("id"))})
        snapshot[str(parameter.get("id"))] = parameter.get("value")

    base = _decimal(rule.get("base_months"), "rule.base_months", blockers)
    for position, adjustment in enumerate(rule.get("adjustments", [])):
        if adjustment.get("legal_review_status") != "approved":
            blockers.append(
                {
                    "code": "adjustment_not_approved",
                    "path": f"rule.adjustments[{position}].legal_review_status",
                    "message": str(adjustment.get("id")),
                }
            )
        if not adjustment.get("source_ids"):
            blockers.append(
                {"code": "adjustment_sources_missing", "path": f"rule.adjustments[{position}].source_ids", "message": str(adjustment.get("id"))}
            )
    if blockers:
        return _blocked(blockers, case_id=payload.get("case_id"), actor_id=payload.get("actor_id"))

    assert base is not None
    current = base
    steps: list[dict[str, Any]] = [
        {
            "id": "base",
            "operation": "base_months",
            "before_months": None,
            "delta_months": None,
            "after_months": float(base),
            "source_ids": rule["source_ids"],
        }
    ]
    for position, adjustment in enumerate(rule.get("adjustments", [])):
        value = _decimal(abs(adjustment.get("value", 0)), f"rule.adjustments[{position}].value", blockers)
        if value is None:
            continue
        operation = adjustment.get("operation")
        direction = Decimal("-1") if adjustment.get("direction") == "decrease" else Decimal("1")
        if operation == "fixed_months":
            delta = value * direction
        elif operation == "percent_of_base":
            delta = base * value * direction
        elif operation == "percent_of_current":
            delta = current * value * direction
        else:
            blockers.append(
                {
                    "code": "operation_unsupported",
                    "path": f"rule.adjustments[{position}].operation",
                    "message": str(operation),
                }
            )
            continue
        before = current
        current += delta
        steps.append(
            {
                "id": adjustment.get("id"),
                "operation": operation,
                "before_months": float(before),
                "delta_months": float(delta),
                "after_months": float(current),
                "source_ids": adjustment["source_ids"],
            }
        )
    if blockers:
        return _blocked(blockers, case_id=payload.get("case_id"), actor_id=payload.get("actor_id"))

    minimum = _decimal(rule.get("minimum_months", 0), "rule.minimum_months", blockers)
    maximum_value = rule.get("maximum_months")
    maximum = _decimal(maximum_value, "rule.maximum_months", blockers) if maximum_value is not None else None
    assert minimum is not None
    bounded = max(minimum, current)
    if maximum is not None:
        bounded = min(maximum, bounded)
    rounded = bounded.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    fine = rule.get("fine")
    return {
        "status": "calculated",
        "case_id": payload.get("case_id"),
        "actor_id": payload.get("actor_id"),
        "rule_version": rule["rule_version"],
        "source_ids": rule["source_ids"],
        "input_snapshot": snapshot,
        "term_months": float(rounded),
        "fine": fine,
        "steps": steps,
        "blockers": [],
        "warnings": ["arithmetic replay only; a qualified human must review the legal inputs, rule selection, and result"],
        "human_review_required": True,
    }


def calculate_case_sentencing(bundle: dict[str, Any], actor_id: str) -> dict[str, Any]:
    baselines = [item for item in (bundle.get("sentencing") or {}).get("actor_baselines", []) if item.get("actor_id") == actor_id]
    if not baselines:
        return _blocked(
            [{"code": "actor_baseline_missing", "path": "sentencing.actor_baselines", "message": actor_id}],
            case_id=bundle.get("case_id"),
            actor_id=actor_id,
        )
    baseline = baselines[0]
    amounts = {item["id"]: item for item in bundle.get("amounts", [])}
    parameters = [amounts[item_id] for item_id in baseline.get("amount_ids", []) if item_id in amounts]
    rule = baseline.get("calculation_rule") or {
        "rule_version": baseline.get("rule_version"),
        "legal_review_status": baseline.get("legal_review_status"),
        "source_ids": baseline.get("source_ids", []),
    }
    return calculate_sentencing(
        {
            "case_id": bundle.get("case_id"),
            "actor_id": actor_id,
            "parameters": parameters,
            "rule": rule,
        }
    )
