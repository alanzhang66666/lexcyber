"""注册表化量刑执行体（P7）：sentencing.v2。

与 metadata 重放路径的区别：计算规则来自 engine.rule_package 的 approved
sentencing 包（INV-RULE-002），输入取 metadata.factsSnapshot 不可变快照
（INV-DATA-OWN-002）。outcome.calculation 冻结量刑 DSL：

    outcome.calculation = {
      "base_months": N                          # 直接基准，或
      "base_tiers": [{"when": pred, "months": N}],   # 按金额/事实择档（首个命中生效）
      "adjustments": [{"id","when": pred|null,      # when 命中才调节（留 trace）
                       "direction":"increase|decrease",
                       "operation":"fixed_months|percent_of_base|percent_of_current",
                       "value":X,"source_ids":[...]}],
      "minimum_months": N, "maximum_months": N,     # 夹逼边界（留痕不静默截断）
      "fine": {...}
    }

steps[] 记录 before→delta→after 全链（§9.5），blocked/not_applicable 不产数字。
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from engine.adapters.module_analysis import ModuleAnalysisError
from engine.rules import registry
from engine.rules.evaluator import PredicateError, build_view, evaluate


def calculate_v2(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = payload.get("metadata") or {}
    snapshot = metadata.get("factsSnapshot")
    if not isinstance(snapshot, dict):
        raise ModuleAnalysisError(
            "FACTS_SNAPSHOT_MISSING",
            "量刑执行缺少不可变事实快照（metadata.factsSnapshot）")
    input_ref = payload.get("input_snapshot_ref") or ""
    facts_version_id = (input_ref[len("facts_version:"):]
                        if input_ref.startswith("facts_version:") else None)

    rules = registry.active_rules("sentencing")
    if not rules:
        raise ModuleAnalysisError("MODULE_RULES_UNAVAILABLE",
                                  "无已会签量刑规则包")

    view = build_view(snapshot)
    actor_id = (metadata.get("sentencing") or {}).get("actorId") \
        or metadata.get("actorId")

    results: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    for rule in rules:
        outcome = rule.get("outcome") or {}
        calc = outcome.get("calculation")
        if not isinstance(calc, dict):
            blockers.append({"code": "CALCULATION_MISSING",
                             "path": f"rules.{rule['ruleId']}.outcome.calculation",
                             "message": "sentencing 规则缺少 calculation 计算块"})
            continue
        applicable = True
        if rule.get("predicate"):
            try:
                applicable, _ = evaluate(rule["predicate"], view)
            except PredicateError as exc:
                blockers.append({"code": exc.code, "path": f"rules.{rule['ruleId']}",
                                 "message": str(exc)})
                continue
        if not applicable:
            continue
        results.append(_compute(rule, calc, view))

    if blockers:
        status = "blocked"
    elif not results:
        status = "not_applicable"
    elif any(r["status"] == "blocked" for r in results):
        status = "blocked"
    else:
        status = "calculated"

    body = {
        "schema_version": "sentencing.v2",
        "module": "sentencing",
        "status": status,
        "case_id": payload.get("case_id"),
        "actor_id": actor_id,
        "facts_version_id": facts_version_id,
        "input_snapshot_ref": input_ref or None,
        "results": results,
        "blockers": blockers,
        "dependency_snapshot": {
            "facts_version_id": facts_version_id,
            "rules": [{"ruleId": r["ruleId"], "ruleVersion": r["ruleVersion"],
                       "contentHash": r["contentHash"]} for r in rules],
        },
        "human_review_required": True,
    }
    return {"final_output": body, "human_approval_required": True}


def _compute(rule: dict[str, Any], calc: dict[str, Any],
             view: dict[str, Any]) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []

    base = _resolve_base(rule, calc, view, steps, blockers)
    current = base
    if current is not None:
        for position, adj in enumerate(calc.get("adjustments") or []):
            fired = True
            if adj.get("when"):
                try:
                    fired, _ = evaluate(adj["when"], view)
                except PredicateError as exc:
                    blockers.append({"code": exc.code,
                                     "path": f"calculation.adjustments[{position}].when",
                                     "message": str(exc)})
                    continue
            if not fired:
                steps.append({"id": adj.get("id"), "operation": "skipped",
                              "reason": "when predicate not fired",
                              "before_months": None, "delta_months": None,
                              "after_months": float(current)})
                continue
            delta = _delta(adj, base, current, position, blockers)
            if delta is None:
                continue
            before = current
            current += delta
            steps.append({"id": adj.get("id"), "operation": adj.get("operation"),
                          "direction": adj.get("direction"),
                          "before_months": float(before), "delta_months": float(delta),
                          "after_months": float(current),
                          "source_ids": adj.get("source_ids", [])})

    bounded_steps: list[dict[str, Any]] = []
    term: Decimal | None = None
    if current is not None and not blockers:
        term = current
        minimum = _num(calc.get("minimum_months"))
        maximum = _num(calc.get("maximum_months"))
        # 法定减轻处罚可低于原法定最低刑：夹逼只在 minimum/maximum 显式给出时应用，
        # 且留痕（不静默截断）。
        if minimum is not None and term < minimum:
            bounded_steps.append({"id": "floor", "operation": "clamp",
                                  "before_months": float(term), "after_months": float(minimum)})
            term = minimum
        if maximum is not None and term > maximum:
            bounded_steps.append({"id": "ceiling", "operation": "clamp",
                                  "before_months": float(term), "after_months": float(maximum)})
            term = maximum
        term = term.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

    result = {
        "ruleId": rule["ruleId"], "ruleVersion": rule["ruleVersion"],
        "contentHash": rule["contentHash"], "sourceIds": rule["sourceIds"],
        "status": "blocked" if blockers or term is None else "calculated",
        "term_months": float(term) if term is not None else None,
        "fine": calc.get("fine"),
        "steps": steps + bounded_steps,
        "blockers": blockers,
    }
    if term is None and not blockers:
        result["blockers"] = [{"code": "BASE_UNRESOLVED",
                               "path": "calculation.base_tiers",
                               "message": "无命中基准档且无 base_months 兜底"}]
        result["status"] = "blocked"
    return result


def _resolve_base(rule: dict[str, Any], calc: dict[str, Any], view: dict[str, Any],
                  steps: list[dict[str, Any]], blockers: list[dict[str, Any]]) -> Decimal | None:
    for position, tier in enumerate(calc.get("base_tiers") or []):
        try:
            fired, _ = evaluate(tier["when"], view)
        except (PredicateError, KeyError) as exc:
            blockers.append({"code": "BASE_TIER_INVALID",
                             "path": f"calculation.base_tiers[{position}]",
                             "message": str(exc)})
            continue
        if fired:
            months = _num(tier.get("months"))
            if months is None:
                blockers.append({"code": "BASE_TIER_MONTHS_INVALID",
                                 "path": f"calculation.base_tiers[{position}].months",
                                 "message": str(tier.get("months"))})
                return None
            steps.append({"id": "base", "operation": "base_tier",
                          "tier_index": position, "before_months": None,
                          "delta_months": None, "after_months": float(months)})
            return months
    months = _num(calc.get("base_months"))
    if months is not None:
        steps.append({"id": "base", "operation": "base_months",
                      "before_months": None, "delta_months": None,
                      "after_months": float(months)})
    return months


def _delta(adj: dict[str, Any], base: Decimal | None, current: Decimal,
         position: int, blockers: list[dict[str, Any]]) -> Decimal | None:
    value = _num(adj.get("value"))
    if value is None:
        blockers.append({"code": "ADJUSTMENT_VALUE_INVALID",
                         "path": f"calculation.adjustments[{position}].value",
                         "message": str(adj.get("value"))})
        return None
    direction = Decimal("-1") if adj.get("direction") == "decrease" else Decimal("1")
    op = adj.get("operation")
    if op == "fixed_months":
        return value * direction
    if op == "percent_of_base" and base is not None:
        return base * value * direction
    if op == "percent_of_current":
        return current * value * direction
    blockers.append({"code": "OPERATION_UNSUPPORTED",
                     "path": f"calculation.adjustments[{position}].operation",
                     "message": str(op)})
    return None


def _num(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value)) if value is not None else None
    except (InvalidOperation, ValueError):
        return None


class SentencingV2Runner:
    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return calculate_v2(payload)
