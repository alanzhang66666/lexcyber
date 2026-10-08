"""模块分析执行体（P6）：合规筛查 / 定罪研判。

从 ExecutionRequest.metadata.factsSnapshot 取不可变输入（INV-DATA-OWN-002），
只消费 legal_review_status=approved 的规则包（INV-RULE-002），产出带依赖快照的
case.compliance.v2 / case.conviction.v2 payload。结论性判断永远要求人工复核：
human_review_required 恒为 true（INV-AI/流程边界）。
"""
from __future__ import annotations

import datetime
import json
import re
from copy import deepcopy
from typing import Any

from engine.adapters import legal_temporal
from engine.rules import registry
from engine.rules.conviction_paths import (
    execute_candidate_paths,
    validate_candidate_path_definitions,
)
from engine.rules.evaluator import PredicateError, build_view, evaluate
from engine.rules.evidence import check_required_evidence
from engine.rules.inputs import InputValidator


class ModuleAnalysisError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


_FAMILIES = {
    "compliance.analyze": ("compliance", "case.compliance.v2", "compliance"),
    "conviction.analyze": ("conviction", "case.conviction.v2", "conviction"),
}


def analyze(payload: dict[str, Any], task_type: str) -> dict[str, Any]:
    family, schema_version, module = _FAMILIES[task_type]
    metadata = payload.get("metadata") or {}
    snapshot = metadata.get("factsSnapshot")
    if not isinstance(snapshot, dict):
        raise ModuleAnalysisError(
            "FACTS_SNAPSHOT_MISSING",
            "模块执行缺少不可变事实快照（metadata.factsSnapshot）")
    try:
        as_of_date = registry.require_as_of_date(metadata)
    except registry.RegistryError as exc:
        raise ModuleAnalysisError(exc.code, str(exc)) from exc
    input_ref = payload.get("input_snapshot_ref") or ""
    facts_version_id = _ref_value(input_ref, "facts_version")
    input_validator = InputValidator(snapshot, build_view(snapshot))
    date_resolution = legal_temporal.resolve_case_dates(snapshot, input_validator)
    conduct_date = date_resolution["conduct"]
    judgment_date = date_resolution["judgment"]
    both_dates = conduct_date is not None and judgment_date is not None

    families = [family]
    if module == "conviction":
        families.append("distinction")  # 定罪研判同时跑界分规则
    rules: list[dict[str, Any]] = []
    missing: list[str] = []
    for fam in families:
        try:
            active = registry.active_rules(fam, as_of_date)
        except registry.RegistryError as exc:
            raise ModuleAnalysisError(exc.code, str(exc)) from exc
        if not active:
            missing.append(fam)
        rules.extend({"family": fam, **r} for r in active)
    primary_rule_blockers: list[dict[str, Any]] = []
    if missing and not both_dates:
        raise ModuleAnalysisError(
            "MODULE_RULES_UNAVAILABLE",
            f"无已会签规则包覆盖 family: {', '.join(missing)}")
    if missing:
        primary_rule_blockers.append({
            "code": "MODULE_RULES_UNAVAILABLE", "families": missing,
            "message": f"主 asOfDate 无已会签规则包覆盖 family: {', '.join(missing)}",
        })

    view = build_view(snapshot)
    rule_results: list[dict[str, Any]] = []
    candidate_paths: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = primary_rule_blockers[:]
    fired_sources: set[str] = set()
    for rule in rules:
        try:
            fired, trace = evaluate(rule["predicate"], view)
            input_blockers = input_validator.check_trace(
                trace, phase=f"rule_predicate:{rule['ruleId']}")
        except PredicateError as exc:
            blockers.append({"code": exc.code, "path": f"rules.{rule['ruleId']}",
                             "message": str(exc)})
            continue
        evidence = _check_required_evidence(rule, snapshot) if fired else {
            "ruleId": rule["ruleId"], "requiredKinds": [], "blockers": []
        }
        if input_blockers:
            blockers.extend(input_blockers)
        declared_path_blockers = validate_candidate_path_definitions(rule.get("outcome"))
        if declared_path_blockers:
            blockers.extend(declared_path_blockers)
        paths_for_rule, path_blockers = execute_candidate_paths(
            rule=rule, snapshot=snapshot, input_validator=input_validator,
            fired=fired, predicate_blockers=input_blockers + evidence.get("blockers", []))
        if paths_for_rule:
            candidate_paths.extend(paths_for_rule)
            blockers.extend(path_blockers)
            fired_sources.update(str(source_id) for path_row in paths_for_rule
                                 for source_id in path_row.get("legal_source_ids", []))
        entry = {
            "ruleId": rule["ruleId"], "ruleVersion": rule["ruleVersion"],
            "family": rule["family"], "fired": fired,
            "status": "blocked" if evidence.get("blockers") or input_blockers else (
                "calculated" if fired else "not_applicable"),
            "trace": trace, "outcome": rule["outcome"] if fired else None,
            "sourceIds": rule["sourceIds"], "contentHash": rule["contentHash"],
            "evidence_checks": evidence,
            "input_blockers": input_blockers,
            "candidate_paths": paths_for_rule,
            "input_validation": input_validator.summary(),
        }
        rule_results.append(entry)
        if fired:
            fired_sources.update(rule["sourceIds"])
            blockers.extend(evidence.get("blockers", []))

    # 双时点法源解析（INV-LEGAL-006）：若快照提供 conduct/judgment 日期，
    # 对 fired 规则绑定的法源做时点解析；跨版本 → divergence 阻断自动择一。
    blockers.extend(date_resolution["blockers"])
    temporal = deepcopy(_resolve_sources(fired_sources, conduct_date, judgment_date))
    divergence = temporal.get("divergence", [])
    blockers.extend(temporal.get("blockers", []))
    temporal_paths = _temporal_paths(
        payload, family, schema_version, module, snapshot, input_ref,
        facts_version_id, conduct_date, judgment_date,
        both_dates, _resolve_sources,
    )
    path_source_ids = {str(source_id) for path in temporal_paths
                       for rule in path.get("rules", [])
                       for source_id in rule.get("sourceIds", [])
                       if rule.get("fired") or rule.get("candidate_paths")}
    if path_source_ids - fired_sources:
        path_temporal = deepcopy(_resolve_sources(path_source_ids, conduct_date, judgment_date))
        divergence.extend(path_temporal.get("divergence", []))
        blockers.extend(path_temporal.get("blockers", []))
        temporal["source_versions"] = _unique_dicts(
            temporal.get("source_versions", []) + path_temporal.get("source_versions", []),
            ("sourceId", "sourceVersion", "point"),
        )
        temporal["resolutions"].update(path_temporal.get("resolutions", {}))
    path_semantics = _path_semantic_results(temporal_paths)
    if len(path_semantics) == 2 and path_semantics[0] != path_semantics[1]:
        divergence.append({"code": "RULE_DATE_PATH_DIVERGENCE",
                           "detail": "行为与裁判时点的规则业务结果不同，须人工择法"})
    for path in temporal_paths:
        candidate_paths.extend(path.get("candidate_paths", []))
        if path.get("blockers"):
            blockers.append({"code": "TEMPORAL_PATH_BLOCKED",
                             "point": path["point"],
                             "blockers": path["blockers"]})
    if divergence:
        blockers.extend({"code": item.get("code", "LEGAL_TEMPORAL_DIVERGENCE"), **item}
                         for item in divergence)

    dependency_rules = [{"ruleId": r["ruleId"], "ruleVersion": r["ruleVersion"],
                         "family": r["family"], "contentHash": r["contentHash"]}
                        for r in rules]
    dependency_sources = set(fired_sources)
    dependency_versions = list(temporal.get("source_versions", []))
    for path in temporal_paths:
        dependency_rules.extend(path["dependency_snapshot"].get("rules", []))
        dependency_versions.extend(path["dependency_snapshot"].get("source_versions", []))
        dependency_sources.update(source_id for rule in path.get("rules", [])
                                  if rule.get("fired") or rule.get("candidate_paths")
                                  for source_id in rule.get("sourceIds", []))
    dependency_rules = _unique_dicts(dependency_rules, ("ruleId", "ruleVersion", "family"))
    dependency_versions = _unique_dicts(dependency_versions,
                                        ("sourceId", "sourceVersion", "point"))

    if module == "conviction" and not _has_confirmed_jurisdiction_connection(
            snapshot, input_validator, point="as_of"):
        blockers.append({
            "code": "JURISDICTION_CONNECTION_UNCONFIRMED",
            "path": "entities.jurisdictionConnections",
            "message": "定罪研判需要至少一个 verificationStatus 为 confirmed 的管辖连接点",
        })
    if module == "conviction" and candidate_paths:
        for point in {item.get("point") for item in candidate_paths}:
            distinct = {(item.get("rule_id"), item.get("rule_version"), item.get("path_id"))
                        for item in candidate_paths if item.get("point") == point}
            if len(distinct) < 2:
                blockers.append({"code": "CONVICTION_PATHS_INCOMPLETE", "point": point,
                                 "message": "至少需要两个不同的已声明 conviction candidate path"})

    input_validation = input_validator.summary()
    for path in temporal_paths:
        path_marker = path.get("input_validation") or {}
        for check in path_marker.get("checks", []):
            if check not in input_validation["checks"]:
                input_validation["checks"].append(check)
        for blocker in path_marker.get("blockers", []):
            if blocker not in input_validation["blockers"]:
                input_validation["blockers"].append(blocker)
    input_validation["status"] = "blocked" if input_validation["blockers"] else "verified"
    blockers.extend(input_validation.get("blockers", []))

    status = "blocked" if blockers else ("calculated" if any(r["fired"] for r in rule_results)
                                         else "not_applicable")
    if blockers:
        # A blocked execution cannot publish a derived candidate/exclusion
        # conclusion, while retaining identifiers and proof diagnostics.
        for path_row in candidate_paths:
            path_row["baseline_position"] = None
            path_row["exclusion_reason"] = None
            path_row["status"] = "blocked"
            if not path_row.get("blockers"):
                path_row["blockers"] = [{
                    "code": "MODULE_BLOCKED",
                    "reason": "module execution is blocked; derived position withheld",
                }]
    result_payload = {
        "schema_version": schema_version,
        "module": module,
        "status": status,
        "case_id": payload.get("case_id"),
        "facts_version_id": facts_version_id,
        "input_snapshot_ref": input_ref or None,
        "rules": rule_results,
        "candidate_paths": candidate_paths,
        "dependency_snapshot": {
            "facts_version_id": facts_version_id,
            "as_of_date": as_of_date.isoformat(),
            "rules": dependency_rules,
            "sources": sorted(dependency_sources),
            "source_versions": dependency_versions,
        },
        "blockers": blockers,
        "divergence": divergence,
        "temporal_paths": temporal_paths,
        "source_resolutions": _source_resolutions(temporal),
        "legal_dates": _legal_dates(date_resolution),
        "human_review_required": True,
        "input_validation": input_validation,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    return {"final_output": result_payload, "human_approval_required": True}


def _ref_value(ref: str, prefix: str) -> str | None:
    return ref[len(prefix) + 1:] if ref.startswith(prefix + ":") else None


def _snapshot_date(view: dict[str, Any], key: str) -> datetime.date | None:
    item = (view.get("facts") or {}).get(key)
    if not isinstance(item, dict):
        return None
    raw = item.get("value")
    if isinstance(raw, dict):
        raw = raw.get("date") or raw.get("value")
    if not isinstance(raw, str):
        return None
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})", raw)
    if not match:
        return None
    try:
        return datetime.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def _date_present(snapshot: dict[str, Any], key: str) -> bool:
    return any(isinstance(item, dict) and item.get("key") == key
               for item in snapshot.get("items") or [])


def _has_confirmed_jurisdiction_connection(snapshot: dict[str, Any],
                                            input_validator: InputValidator | None = None,
                                            *, point: str = "as_of") -> bool:
    entities = snapshot.get("entities")
    if not isinstance(entities, dict):
        return False
    connections = entities.get("jurisdictionConnections")
    if not isinstance(connections, list):
        return False
    diagnostics: list[dict[str, Any]] = []
    for index, connection in enumerate(connections):
        if not isinstance(connection, dict) or connection.get("verificationStatus") != "confirmed":
            continue
        if input_validator is None:
            return True
        probe = InputValidator(snapshot, build_view(snapshot))
        probe.check_path(f"entities.jurisdictionConnections.items.{index}",
                         phase="jurisdiction", point=point)
        summary = probe.summary()
        if not summary["blockers"]:
            input_validator.merge_summary(summary)
            return True
        diagnostics.append(summary)
    for summary in diagnostics:
        input_validator.merge_summary(summary)
    return False


def _resolve_sources(source_ids: set[str], conduct: datetime.date | None,
                     judgment: datetime.date | None) -> dict[str, Any]:
    return legal_temporal.resolve_sources(source_ids, conduct, judgment)


def _check_required_evidence(rule: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    return check_required_evidence(rule, snapshot)


def _temporal_paths(payload: dict[str, Any], family: str, schema_version: str,
                    module: str, snapshot: dict[str, Any], input_ref: str,
                    facts_version_id: str | None, conduct: datetime.date | None,
                    judgment: datetime.date | None, divergent: bool,
                    source_resolver=legal_temporal.resolve_sources) -> list[dict[str, Any]]:
    """Execute both approved date paths when the two legal points diverge."""
    if not divergent or conduct is None or judgment is None:
        return []
    paths: list[dict[str, Any]] = []
    view = build_view(snapshot)
    families = [family] + (["distinction"] if module == "conviction" else [])
    for point, point_date in (("conduct", conduct), ("judgment", judgment)):
        input_validator = InputValidator(snapshot, view)
        date_names = ("conduct_date", "offense_date") if point == "conduct" else ("judgment_date",)
        for date_name in date_names:
            if _date_present(snapshot, date_name):
                input_validator.check_path(f"facts.{date_name}.value",
                                           phase="legal_dates", point=point)
        path_rules: list[dict[str, Any]] = []
        path_blockers: list[dict[str, Any]] = []
        if module == "conviction" and not _has_confirmed_jurisdiction_connection(
                snapshot, input_validator, point=point):
            path_blockers.append({
                "code": "JURISDICTION_CONNECTION_UNCONFIRMED",
                "path": "entities.jurisdictionConnections",
                "message": "定罪研判路径需要至少一个 confirmed 的管辖连接点",
            })
        for fam in families:
            try:
                active = registry.active_rules(fam, point_date)
            except registry.RegistryError as exc:
                path_blockers.append({"code": exc.code, "message": str(exc)})
                continue
            if not active:
                path_blockers.append({"code": "TEMPORAL_RULE_PATH_UNAVAILABLE",
                                      "point": point, "family": fam,
                                      "date": point_date.isoformat(),
                                      "message": f"该时点没有已会签 {fam} 规则包覆盖"})
            path_rules.extend({"family": fam, **rule} for rule in active)
        path_results: list[dict[str, Any]] = []
        path_candidate_paths: list[dict[str, Any]] = []
        for rule in path_rules:
            try:
                fired, trace = evaluate(rule["predicate"], view)
                input_blockers = input_validator.check_trace(
                    trace, phase=f"rule_predicate:{rule['ruleId']}", point=point)
            except PredicateError as exc:
                path_blockers.append({"code": exc.code, "path": f"rules.{rule['ruleId']}",
                                      "message": str(exc)})
                continue
            evidence = _check_required_evidence(rule, snapshot) if fired else {
                "ruleId": rule["ruleId"], "requiredKinds": [], "blockers": []
            }
            if input_blockers:
                path_blockers.extend(input_blockers)
            if fired:
                path_blockers.extend(evidence.get("blockers", []))
            declared_path_blockers = validate_candidate_path_definitions(rule.get("outcome"))
            path_blockers.extend(declared_path_blockers)
            paths_for_rule, candidate_blockers = execute_candidate_paths(
                rule=rule, snapshot=snapshot, input_validator=input_validator,
                fired=fired, point=point,
                predicate_blockers=input_blockers + evidence.get("blockers", []))
            path_candidate_paths.extend(paths_for_rule)
            path_blockers.extend(candidate_blockers)
            path_results.append({"ruleId": rule["ruleId"], "ruleVersion": rule["ruleVersion"],
                                 "family": rule["family"], "fired": fired, "trace": trace,
                                 "status": "blocked" if evidence.get("blockers") or input_blockers else (
                                     "calculated" if fired else "not_applicable"),
                                 "outcome": rule["outcome"] if fired else None,
                                 "sourceIds": rule["sourceIds"], "contentHash": rule["contentHash"],
                                 "evidence_checks": evidence,
                                 "input_blockers": input_blockers,
                                 "candidate_paths": paths_for_rule,
                                 "input_validation": input_validator.summary()})
        if not path_rules and not path_blockers:
            path_blockers.append({"code": "TEMPORAL_RULE_PATH_UNAVAILABLE",
                                  "point": point, "date": point_date.isoformat(),
                                  "message": "该时点没有已会签规则包覆盖"})
        path_sources = deepcopy(source_resolver(
            {str(source_id) for rule in path_results
             if rule.get("fired") or rule.get("candidate_paths")
             for source_id in rule.get("sourceIds", [])},
            point_date if point == "conduct" else None,
            point_date if point == "judgment" else None,
        ))
        path_blockers.extend(legal_temporal.temporal_blockers(path_sources))
        path_input_validation = input_validator.summary()
        path_status = "blocked" if path_blockers or path_input_validation.get("blockers") else (
            "calculated" if any(rule["fired"] for rule in path_results) else "not_applicable")
        if module == "conviction" and path_candidate_paths:
            distinct = {(item.get("rule_id"), item.get("rule_version"), item.get("path_id"))
                        for item in path_candidate_paths}
            if len(distinct) < 2:
                path_blockers.append({"code": "CONVICTION_PATHS_INCOMPLETE", "point": point,
                                      "message": "至少需要两个不同的已声明 conviction candidate path"})
                path_status = "blocked"
        path_blockers.extend(path_input_validation.get("blockers", []))
        paths.append({"point": point, "as_of_date": point_date.isoformat(),
                      "status": path_status,
                      "rules": path_results, "blockers": path_blockers,
                      "candidate_paths": path_candidate_paths,
                      "input_validation": path_input_validation,
                      "dependency_snapshot": {"facts_version_id": facts_version_id,
                                                "as_of_date": point_date.isoformat(),
                                                "rules": [{"ruleId": r["ruleId"],
                                                           "ruleVersion": r["ruleVersion"],
                                                           "family": r["family"],
                                                           "contentHash": r["contentHash"]}
                                                          for r in path_rules],
                                                "source_versions": path_sources.get("source_versions", [])}})
    return paths


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
        outcomes = [{"outcome": _semantic_outcome(rule.get("outcome")), "status": rule.get("status")}
                    for rule in path.get("rules", []) if rule.get("fired")]
        outcomes.extend({key: item.get(key) for key in
                         ("path_id", "actor_id", "charge_key", "baseline_position",
                          "verification_status", "status", "exclusion_reason")}
                        for item in path.get("candidate_paths", []))
        semantic.append(json.dumps(sorted(outcomes, key=lambda item: json.dumps(
            item, ensure_ascii=False, sort_keys=True)), ensure_ascii=False, sort_keys=True))
    return semantic


def _semantic_outcome(outcome: Any) -> Any:
    """Drop declaration metadata from fired-rule business semantics."""
    if not isinstance(outcome, dict):
        return outcome
    return {key: value for key, value in outcome.items() if key != "candidate_paths"}


class ComplianceRunner:
    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return analyze(payload, "compliance.analyze")


class ConvictionRunner:
    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return analyze(payload, "conviction.analyze")
