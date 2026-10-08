"""Explicit requested-charge coverage checks for conviction analysis."""
from __future__ import annotations

from typing import Any


def parse_requested_charges(raw: Any) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    if raw is None:
        return [], []
    if not isinstance(raw, list) or len(raw) > 32:
        return [], [{"code": "INVALID_REQUESTED_CHARGES", "reason": "requestedCharges must be an array of at most 32 items"}]
    if not raw:
        return [], []
    result: list[dict[str, Any]] = []
    blockers: list[dict[str, str]] = []
    seen_keys: set[str] = set()
    seen_raw: set[str] = set()
    for index, item in enumerate(raw):
        path = f"metadata.requestedCharges[{index}]"
        if not isinstance(item, dict) or set(item) - {"requestedCharge", "chargeKey"}:
            blockers.append({"code": "INVALID_REQUESTED_CHARGES", "reason": f"{path} has invalid shape"})
            continue
        requested = item.get("requestedCharge")
        if not isinstance(requested, str) or not requested.strip() or len(requested) > 200:
            blockers.append({"code": "INVALID_REQUESTED_CHARGES", "reason": f"{path}.requestedCharge must be nonblank and <=200 characters"})
            continue
        charge_key = item.get("chargeKey")
        if charge_key is not None and (not isinstance(charge_key, str) or not charge_key.strip() or len(charge_key) > 200):
            blockers.append({"code": "INVALID_REQUESTED_CHARGES", "reason": f"{path}.chargeKey must be null or a nonblank string <=200 characters"})
            continue
        key = charge_key if isinstance(charge_key, str) else None
        raw_key = requested
        if key and key in seen_keys:
            blockers.append({"code": "INVALID_REQUESTED_CHARGES", "reason": f"duplicate chargeKey: {key}"})
        if key:
            seen_keys.add(key)
        elif raw_key in seen_raw:
            blockers.append({"code": "INVALID_REQUESTED_CHARGES", "reason": f"duplicate requestedCharge without chargeKey: {raw_key}"})
        if not key:
            seen_raw.add(raw_key)
        result.append(dict(item))
    return result, blockers


def coverage_for_rules(requests: list[dict[str, Any]], rules: list[dict[str, Any]], *, point: str,
                       date: str | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    covered: dict[str, list[dict[str, Any]]] = {}
    for rule in rules:
        coverage = rule.get("coverage") or {}
        keys = coverage.get("covers", []) if isinstance(coverage, dict) else []
        if not isinstance(keys, list):
            continue
        meta = {"ruleId": rule.get("ruleId"), "ruleVersion": rule.get("ruleVersion"),
                "contentHash": rule.get("contentHash"), "sourceIds": list(rule.get("sourceIds") or [])}
        for key in keys:
            if isinstance(key, str):
                covered.setdefault(key, []).append(meta)
    checks: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for index, request in enumerate(requests):
        key = request.get("chargeKey")
        matches = covered.get(key, []) if isinstance(key, str) and key else []
        checks.append({"point": point, "date": date, "requested_charge": request["requestedCharge"],
                       "charge_key": key, "covered": bool(matches), "rule_versions": matches})
        if not matches:
            missing.append({"id": f"charge:{point}:{index}:{key or request['requestedCharge']}",
                            "missing_item": "charge_out_of_coverage", "kind": "charge_out_of_coverage",
                            "requested_charge": request["requestedCharge"], "charge_key": key,
                            "point": point, "date": date, "status": "blocked",
                            "reason": "requested charge has no approved rule coverage at this legal point"})
    return checks, missing


def coverage_keys_for_rules(rules: list[dict[str, Any]]) -> set[str]:
    keys: set[str] = set()
    for rule in rules:
        coverage = rule.get("coverage") if isinstance(rule, dict) else None
        covers = coverage.get("covers") if isinstance(coverage, dict) else None
        if not isinstance(covers, list):
            continue
        keys.update(item for item in covers if isinstance(item, str))
    return keys


def missing_plan_items(rules: list[dict[str, Any]], coverage_keys: set[str], *, point: str,
                       date: str | None) -> list[dict[str, Any]]:
    missing: list[dict[str, Any]] = []
    for rule in rules:
        outcome = rule.get("outcome") if isinstance(rule, dict) else None
        plans = outcome.get("candidate_paths") if isinstance(outcome, dict) else None
        if not isinstance(plans, list):
            continue
        for index, plan in enumerate(plans):
            if not isinstance(plan, dict):
                continue
            key = plan.get("charge_key")
            if isinstance(key, str) and key in coverage_keys:
                continue
            output_key = key if isinstance(key, str) else None
            missing.append({"id": f"plan:{point}:{rule.get('ruleId')}:{rule.get('ruleVersion')}:{index}",
                            "missing_item": "charge_out_of_coverage", "kind": "charge_out_of_coverage",
                            "requested_charge": None, "charge_key": output_key, "point": point, "date": date,
                            "status": "blocked", "reason": "declared candidate plan has no approved coverage"})
    return missing


def plan_coverage_rule_versions(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return approved rule provenance for explicitly declared plan charge keys."""
    refs: list[dict[str, Any]] = []
    declared: set[str] = set()
    for rule in rules:
        outcome = rule.get("outcome") if isinstance(rule, dict) else None
        plans = outcome.get("candidate_paths", []) if isinstance(outcome, dict) else []
        if isinstance(plans, list):
            declared.update(plan.get("charge_key") for plan in plans
                            if isinstance(plan, dict) and isinstance(plan.get("charge_key"), str))
    for rule in rules:
        coverage = rule.get("coverage") if isinstance(rule, dict) else None
        covers = coverage.get("covers") if isinstance(coverage, dict) else None
        if not isinstance(covers, list):
            continue
        keys = {item for item in covers if isinstance(item, str)}
        if declared & keys:
            refs.append({"ruleId": rule.get("ruleId"), "ruleVersion": rule.get("ruleVersion"),
                         "contentHash": rule.get("contentHash"), "sourceIds": list(rule.get("sourceIds") or [])})
    return refs
