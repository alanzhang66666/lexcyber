from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from engine.adapters.case_bundle import load_case_bundle
from engine.adapters.t1_contract import map_sentencing_result_to_t1
from engine.settings import settings


class SentencingUnavailable(Exception):
    code = "SENTENCING_UNAVAILABLE"

    def __init__(self, message: str = "sentencing calculation is not enabled before T3 legal sign-off") -> None:
        super().__init__(message)


class SentencingInputError(ValueError):
    def __init__(self, code: str, path: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.path = path
        self.message = message

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "path": self.path, "message": self.message, "retryable": False}


def _reviewed_rule_outline(rule: dict[str, Any]) -> dict[str, Any]:
    return {
        key: rule[key]
        for key in (
            "source_document_id",
            "source_section",
            "source_pages",
            "base_range_months",
            "base_months_approximate",
            "base_derivation",
            "adjustments",
            "declared_disposition",
        )
        if key in rule
    }


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
    rule: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
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
    if rule:
        result["rule_version"] = rule.get("rule_version")
        result["source_ids"] = rule.get("source_ids", [])
        result["reviewed_rule_outline"] = _reviewed_rule_outline(rule)
    return result


def calculate_sentencing(payload: dict[str, Any]) -> dict[str, Any]:
    """Replay a legally approved rule with confirmed inputs; otherwise fail closed."""

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
    for position, blocker in enumerate(rule.get("execution_blockers", [])):
        if not isinstance(blocker, dict) or not blocker.get("code") or not blocker.get("message"):
            blockers.append(
                {
                    "code": "execution_blocker_invalid",
                    "path": f"rule.execution_blockers[{position}]",
                    "message": "each execution blocker requires code and message",
                }
            )
            continue
        blockers.append(
            {
                "code": str(blocker["code"]),
                "path": str(blocker.get("path") or f"rule.execution_blockers[{position}]"),
                "message": str(blocker["message"]),
            }
        )

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

    if rule.get("rule_type") == "reviewed_disposition":
        disposition = rule.get("declared_disposition") or {}
        if not disposition:
            blockers.append(
                {
                    "code": "declared_disposition_missing",
                    "path": "rule.declared_disposition",
                    "message": "reviewed disposition replay requires a declared disposition",
                }
            )
        if blockers:
            return _blocked(
                blockers,
                case_id=payload.get("case_id"),
                actor_id=payload.get("actor_id"),
                rule=rule,
            )
        audit_steps = [
            {
                "id": adjustment.get("id"),
                "operation": "reviewed_factor",
                "direction": adjustment.get("direction"),
                "value": adjustment.get("value"),
                "source_ids": adjustment.get("source_ids", []),
            }
            for adjustment in rule.get("adjustments", [])
        ]
        return {
            "status": "calculated",
            "calculation_mode": "reviewed_disposition_replay",
            "case_id": payload.get("case_id"),
            "actor_id": payload.get("actor_id"),
            "rule_version": rule["rule_version"],
            "source_ids": rule["source_ids"],
            "reviewed_rule_outline": _reviewed_rule_outline(rule),
            "input_snapshot": snapshot,
            "term_months": disposition.get("term_months"),
            "term_range_months": disposition.get("term_range_months"),
            "term_lower_kind": disposition.get("term_lower_kind"),
            "term_upper_kind": disposition.get("term_upper_kind"),
            "fine": disposition.get("fine_cny"),
            "fine_range_cny": disposition.get("fine_range_cny"),
            "recovery_cny": disposition.get("recovery_cny"),
            "steps": audit_steps,
            "blockers": [],
            "warnings": [
                "replays the legal-review declared disposition; listed factors are preserved for audit and are not recomputed as a synthetic formula"
            ],
            "human_review_required": True,
        }

    base_value = rule.get("base_months")
    base = _decimal(base_value, "rule.base_months", blockers) if base_value is not None else None
    if base is None and rule.get("legal_review_status") == "approved":
        blockers.append(
            {
                "code": "base_months_missing",
                "path": "rule.base_months",
                "message": "an approved executable rule requires one numeric base_months value",
            }
        )
    for position, adjustment in enumerate(rule.get("adjustments", [])):
        if rule.get("legal_review_status") == "approved" and adjustment.get("legal_review_status") != "approved":
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
        return _blocked(
            blockers,
            case_id=payload.get("case_id"),
            actor_id=payload.get("actor_id"),
            rule=rule,
        )

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
            blockers.append({"code": "operation_unsupported", "path": f"rule.adjustments[{position}].operation", "message": str(operation)})
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
    return {
        "status": "calculated",
        "case_id": payload.get("case_id"),
        "actor_id": payload.get("actor_id"),
        "rule_version": rule["rule_version"],
        "source_ids": rule["source_ids"],
        "input_snapshot": snapshot,
        "term_months": float(rounded),
        "fine": rule.get("fine"),
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
    return calculate_sentencing({"case_id": bundle.get("case_id"), "actor_id": actor_id, "parameters": parameters, "rule": rule})


def calculate(payload: dict[str, Any]) -> dict[str, Any]:
    """T1 task adapter; disabled until T3 legal sign-off enables it."""

    if not settings.sentencing_enabled:
        raise SentencingUnavailable()
    server_case_id = str(payload.get("case_id") or "")
    if not server_case_id:
        raise SentencingInputError("CASE_ID_MISSING", "case_id", "T1 CaseView.id is required")
    metadata = payload.get("metadata") or {}
    sentencing = metadata.get("sentencing")
    if not isinstance(sentencing, dict):
        raise SentencingInputError("SENTENCING_INPUT_MISSING", "metadata.sentencing", "metadata.sentencing must be an object")
    dataset_case_id = str(sentencing.get("datasetCaseId") or sentencing.get("dataset_case_id") or "")
    actor_id = str(sentencing.get("actorId") or sentencing.get("actor_id") or "")
    if not dataset_case_id:
        raise SentencingInputError("DATASET_CASE_ID_MISSING", "metadata.sentencing.datasetCaseId", "T3 dataset case id is required")
    if not actor_id:
        raise SentencingInputError("ACTOR_ID_MISSING", "metadata.sentencing.actorId", "actor id is required")

    if "rule" in sentencing or "parameters" in sentencing:
        result = calculate_sentencing(
            {
                "case_id": str(sentencing.get("t3BundleId") or dataset_case_id),
                "actor_id": actor_id,
                "parameters": sentencing.get("parameters", []),
                "rule": sentencing.get("rule", {}),
            }
        )
    else:
        try:
            bundle = load_case_bundle(str(sentencing.get("t3BundleId") or dataset_case_id))
        except KeyError as exc:
            raise SentencingInputError("SENTENCING_CASE_UNSUPPORTED", "metadata.sentencing.datasetCaseId", dataset_case_id) from exc
        result = calculate_case_sentencing(bundle, actor_id)

    mapped = map_sentencing_result_to_t1(result, case_id=server_case_id, dataset_case_id=dataset_case_id)
    return {"final_output": mapped["content"], "human_approval_required": mapped["taskStatus"] == "waiting_review"}


class SentencingRunner:
    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return calculate(payload)
