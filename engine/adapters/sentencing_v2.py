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

import json
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from engine.adapters import legal_temporal
from engine.adapters.module_analysis import ModuleAnalysisError
from engine.rules import registry
from engine.rules.evaluator import PredicateError, build_view, evaluate
from engine.rules.evidence import check_required_evidence


def calculate_v2(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = payload.get("metadata") or {}
    snapshot = metadata.get("factsSnapshot")
    if not isinstance(snapshot, dict):
        raise ModuleAnalysisError(
            "FACTS_SNAPSHOT_MISSING",
            "量刑执行缺少不可变事实快照（metadata.factsSnapshot）")
    try:
        as_of_date = registry.require_as_of_date(metadata)
    except registry.RegistryError as exc:
        raise ModuleAnalysisError(exc.code, str(exc)) from exc
    input_ref = payload.get("input_snapshot_ref") or ""
    facts_version_id = (input_ref[len("facts_version:"):]
                        if input_ref.startswith("facts_version:") else None)
    date_resolution = legal_temporal.resolve_case_dates(snapshot)
    conduct_date = date_resolution["conduct"]
    judgment_date = date_resolution["judgment"]
    both_dates = conduct_date is not None and judgment_date is not None
    artifact_versions = metadata.get("artifactVersions") or {}
    conviction_version_id = artifact_versions.get("conviction")
    if not isinstance(conviction_version_id, str) or not conviction_version_id:
        raise ModuleAnalysisError(
            "CONVICTION_NOT_CONFIRMED",
            "量刑执行缺少派发时冻结的有效定罪工件版本")

    try:
        rules = registry.active_rules("sentencing", as_of_date)
    except registry.RegistryError as exc:
        raise ModuleAnalysisError(exc.code, str(exc)) from exc
    primary_rule_blockers: list[dict[str, Any]] = []
    if not rules and not both_dates:
        raise ModuleAnalysisError("MODULE_RULES_UNAVAILABLE",
                                  "无已会签量刑规则包")
    if not rules:
        primary_rule_blockers.append({"code": "MODULE_RULES_UNAVAILABLE",
                                      "message": "主 asOfDate 无已会签量刑规则包"})

    view = build_view(snapshot)
    actor_id = (metadata.get("sentencing") or {}).get("actorId") \
        or metadata.get("actorId")

    results: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = primary_rule_blockers[:]
    applicable_rules: list[dict[str, Any]] = []
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
        applicable_rules.append(rule)
        evidence = _check_required_evidence(rule, snapshot)
        if evidence.get("blockers"):
            blockers.extend(evidence["blockers"])
            results.append(_blocked_result(rule, evidence["blockers"], evidence))
            continue
        computed = _compute(rule, calc, view)
        computed["evidence_checks"] = evidence
        results.append(computed)

    blockers.extend(date_resolution["blockers"])
    source_ids = {str(source_id) for result in results
                  for source_id in result.get("sourceIds", [])}
    temporal = legal_temporal.resolve_sources(source_ids, conduct_date, judgment_date)
    temporal_paths = _temporal_paths(snapshot, metadata, payload.get("case_id"),
                                     input_ref, facts_version_id, conviction_version_id,
                                     conduct_date, judgment_date, both_dates)
    path_source_ids = {str(source_id) for path in temporal_paths
                       for result in path.get("results", [])
                       for source_id in result.get("sourceIds", [])}
    if path_source_ids - source_ids:
        path_temporal = legal_temporal.resolve_sources(path_source_ids, conduct_date, judgment_date)
        temporal["divergence"] = temporal.get("divergence", []) + path_temporal.get("divergence", [])
        temporal["source_versions"] = _unique_dicts(
            temporal.get("source_versions", []) + path_temporal.get("source_versions", []),
            ("sourceId", "sourceVersion", "point"),
        )
        temporal["resolutions"].update(path_temporal.get("resolutions", {}))
        blockers.extend(path_temporal.get("blockers", []))
    if _path_semantic_results(temporal_paths):
        semantics = _path_semantic_results(temporal_paths)
        if len(semantics) == 2 and semantics[0] != semantics[1]:
            temporal["divergence"].append({
                "code": "RULE_DATE_PATH_DIVERGENCE",
                "detail": "行为与裁判时点的量刑业务结果不同，须人工择法",
            })
    blockers.extend(legal_temporal.temporal_blockers(temporal))
    for path in temporal_paths:
        path_blockers = list(path.get("blockers", []))
        for result in path.get("results", []):
            if result.get("status") == "blocked":
                for blocker in result.get("blockers", []):
                    item = {"ruleId": result.get("ruleId"), **blocker}
                    if item not in path_blockers:
                        path_blockers.append(item)
        if path.get("status") == "blocked":
            blockers.append({"code": "TEMPORAL_PATH_BLOCKED",
                             "point": path["point"],
                             "blockers": path_blockers})

    if blockers:
        status = "blocked"
    elif not results:
        status = "not_applicable"
    elif any(r["status"] == "blocked" for r in results):
        status = "blocked"
    else:
        status = "calculated"

    # A temporal dispute/coverage problem must never expose a usable sentence.
    if blockers:
        for result in results:
            result["term_months"] = None
            result["fine"] = None
        for path in temporal_paths:
            if path.get("status") == "blocked":
                for result in path.get("results", []):
                    result["term_months"] = None
                    result["fine"] = None

    dependency_rules = [{"ruleId": r["ruleId"], "ruleVersion": r["ruleVersion"],
                         "family": "sentencing",
                         "contentHash": r["contentHash"]} for r in rules]
    dependency_versions = list(temporal.get("source_versions", []))
    dependency_sources = set(source_ids)
    for path in temporal_paths:
        dependency_rules.extend(path["dependency_snapshot"].get("rules", []))
        dependency_versions.extend(path["dependency_snapshot"].get("source_versions", []))
        dependency_sources.update(source_id for result in path.get("results", [])
                                  for source_id in result.get("sourceIds", []))
    dependency_rules = _unique_dicts(dependency_rules, ("ruleId", "ruleVersion", "family"))
    dependency_versions = _unique_dicts(dependency_versions,
                                        ("sourceId", "sourceVersion", "point"))

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
            "as_of_date": as_of_date.isoformat(),
            "artifacts": [{"module": "conviction",
                            "artifactVersionId": conviction_version_id}],
            "rules": dependency_rules,
            "sources": sorted(dependency_sources),
            "source_versions": dependency_versions,
        },
        "human_review_required": True,
        "source_resolutions": _source_resolutions(temporal),
        "legal_dates": _legal_dates(date_resolution),
        "temporal_paths": temporal_paths,
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
        "contentHash": rule["contentHash"], "sourceIds": _participating_source_ids(rule, calc, view),
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


def _blocked_result(rule: dict[str, Any], blockers: list[dict[str, Any]],
                    evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "ruleId": rule["ruleId"], "ruleVersion": rule["ruleVersion"],
        "contentHash": rule["contentHash"], "sourceIds": rule["sourceIds"],
        "status": "blocked", "term_months": None, "fine": None, "steps": [],
        "blockers": blockers, "evidence_checks": evidence or {},
    }


def _participating_source_ids(rule: dict[str, Any], calc: dict[str, Any],
                              view: dict[str, Any]) -> list[str]:
    """Retain package sources and only sources of fired components."""
    ids = {str(source_id) for source_id in rule.get("sourceIds", [])}
    tier_fired = False
    for tier in calc.get("base_tiers") or []:
        try:
            fired, _ = evaluate(tier["when"], view)
        except (PredicateError, KeyError):
            continue
        if fired:
            tier_fired = True
            ids.update(str(source_id) for source_id in tier.get("source_ids", []))
            break
    if not tier_fired:
        ids.update(str(source_id) for source_id in calc.get("source_ids", []))
    for adjustment in calc.get("adjustments") or []:
        fired = True
        if adjustment.get("when"):
            try:
                fired, _ = evaluate(adjustment["when"], view)
            except PredicateError:
                fired = False
        if fired:
            ids.update(str(source_id) for source_id in adjustment.get("source_ids", []))
    return sorted(ids)


def _check_required_evidence(rule: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    return check_required_evidence(rule, snapshot)


def _source_resolutions(temporal: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for source_key, resolution in (temporal.get("resolutions") or {}).items():
        row = {"sourceKey": source_key,
               "coverageGap": bool(resolution.get("coverageGap")),
               "divergence": resolution.get("divergence", []),
               "overlap": bool(resolution.get("overlap")),
               "overlaps": resolution.get("overlaps", [])}
        for point in ("conduct", "judgment"):
            law = resolution.get(f"{point}_law")
            if law is not None:
                row[f"{point}_law"] = law
        rows.append(row)
    return rows


def _legal_dates(resolution: dict[str, Any]) -> dict[str, Any]:
    return {
        "conduct": resolution["conduct"].isoformat() if resolution["conduct"] else None,
        "judgment": resolution["judgment"].isoformat() if resolution["judgment"] else None,
        "missing": resolution.get("missing", []),
        "conflicts": resolution.get("conflicts", []),
        "blockers": resolution.get("blockers", []),
    }


def _unique_dicts(items: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for item in items:
        unique[tuple(item.get(key) for key in keys)] = item
    return list(unique.values())


def _path_semantic_results(paths: list[dict[str, Any]]) -> list[str]:
    semantic: list[str] = []
    for path in paths:
        results = [{"term_months": result.get("term_months"),
                    "fine": result.get("fine"),
                    "status": result.get("status")}
                   for result in path.get("results", [])
                   if result.get("status") == "calculated"]
        semantic.append(json.dumps(results, ensure_ascii=False, sort_keys=True))
    return semantic


def _temporal_paths(snapshot: dict[str, Any], metadata: dict[str, Any], case_id: Any,
                    input_ref: str, facts_version_id: str | None,
                    conviction_version_id: str, conduct, judgment,
                    divergent: bool) -> list[dict[str, Any]]:
    if not divergent or conduct is None or judgment is None:
        return []
    paths = []
    view = build_view(snapshot)
    for point, point_date in (("conduct", conduct), ("judgment", judgment)):
        blockers: list[dict[str, Any]] = []
        try:
            path_rules = registry.active_rules("sentencing", point_date)
        except registry.RegistryError as exc:
            path_rules = []
            blockers.append({"code": exc.code, "point": point,
                             "message": str(exc)})
        path_results: list[dict[str, Any]] = []
        for rule in path_rules:
            try:
                applicable, _ = evaluate(rule["predicate"], view) if rule.get("predicate") else (True, [])
            except PredicateError as exc:
                blockers.append({"code": exc.code, "path": f"rules.{rule['ruleId']}",
                                 "message": str(exc)})
                continue
            if not applicable:
                continue
            evidence = _check_required_evidence(rule, snapshot)
            calc = (rule.get("outcome") or {}).get("calculation")
            if evidence.get("blockers"):
                blockers.extend(evidence["blockers"])
                path_results.append(_blocked_result(rule, evidence["blockers"], evidence))
            elif not isinstance(calc, dict):
                blocker = {"code": "CALCULATION_MISSING",
                           "path": f"rules.{rule['ruleId']}.outcome.calculation",
                           "message": "sentencing 规则缺少 calculation 计算块"}
                blockers.append(blocker)
                path_results.append(_blocked_result(rule, [blocker], evidence))
            else:
                result = _compute(rule, calc, view)
                result["evidence_checks"] = evidence
                path_results.append(result)
                if result["status"] == "blocked":
                    blockers.extend({"ruleId": rule["ruleId"], **blocker}
                                    for blocker in result.get("blockers", []))
        if not path_rules:
            blockers.append({"code": "TEMPORAL_RULE_PATH_UNAVAILABLE", "point": point,
                             "date": point_date.isoformat(),
                             "message": "该时点没有已会签量刑规则包覆盖"})
        path_source_ids = {str(source_id) for result in path_results
                           for source_id in result.get("sourceIds", [])}
        path_sources = legal_temporal.resolve_sources(
            path_source_ids,
            point_date if point == "conduct" else None,
            point_date if point == "judgment" else None,
        )
        blockers.extend(legal_temporal.temporal_blockers(path_sources))
        path_status = "blocked" if blockers or any(r["status"] == "blocked" for r in path_results) else (
            "calculated" if path_results else "not_applicable")
        if path_status == "blocked":
            for result in path_results:
                result["term_months"] = None
                result["fine"] = None
        paths.append({"point": point, "as_of_date": point_date.isoformat(),
                      "status": path_status, "results": path_results,
                      "blockers": blockers,
                      "dependency_snapshot": {
                          "facts_version_id": facts_version_id,
                          "as_of_date": point_date.isoformat(),
                          "artifacts": [{"module": "conviction",
                                          "artifactVersionId": conviction_version_id}],
                          "rules": [{"ruleId": r["ruleId"], "ruleVersion": r["ruleVersion"],
                                     "family": "sentencing",
                                     "contentHash": r["contentHash"]} for r in path_rules],
                          "source_versions": path_sources.get("source_versions", []),
                      }})
    return paths


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
