"""模块分析执行体（P6）：合规筛查 / 定罪研判。

从 ExecutionRequest.metadata.factsSnapshot 取不可变输入（INV-DATA-OWN-002），
只消费 legal_review_status=approved 的规则包（INV-RULE-002），产出带依赖快照的
case.compliance.v2 / case.conviction.v2 payload。结论性判断永远要求人工复核：
human_review_required 恒为 true（INV-AI/流程边界）。
"""
from __future__ import annotations

import datetime
import re
from typing import Any

from engine.rules import registry
from engine.rules.evaluator import PredicateError, build_view, evaluate


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
    input_ref = payload.get("input_snapshot_ref") or ""
    facts_version_id = _ref_value(input_ref, "facts_version")

    families = [family]
    if module == "conviction":
        families.append("distinction")  # 定罪研判同时跑界分规则
    rules: list[dict[str, Any]] = []
    missing: list[str] = []
    for fam in families:
        active = registry.active_rules(fam)
        if not active:
            missing.append(fam)
        rules.extend({"family": fam, **r} for r in active)
    if missing:
        raise ModuleAnalysisError(
            "MODULE_RULES_UNAVAILABLE",
            f"无已会签规则包覆盖 family: {', '.join(missing)}")

    view = build_view(snapshot)
    rule_results: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    fired_sources: set[str] = set()
    for rule in rules:
        try:
            fired, trace = evaluate(rule["predicate"], view)
        except PredicateError as exc:
            blockers.append({"code": exc.code, "path": f"rules.{rule['ruleId']}",
                             "message": str(exc)})
            continue
        entry = {
            "ruleId": rule["ruleId"], "ruleVersion": rule["ruleVersion"],
            "family": rule["family"], "fired": fired,
            "trace": trace, "outcome": rule["outcome"] if fired else None,
            "sourceIds": rule["sourceIds"], "contentHash": rule["contentHash"],
        }
        rule_results.append(entry)
        if fired:
            fired_sources.update(rule["sourceIds"])

    # 双时点法源解析（INV-LEGAL-006）：若快照提供 conduct/judgment 日期，
    # 对 fired 规则绑定的法源做时点解析；跨版本 → divergence 阻断自动择一。
    divergence: list[dict[str, Any]] = []
    conduct_date = _snapshot_date(view, "conduct_date") or _snapshot_date(view, "offense_date")
    judgment_date = _snapshot_date(view, "judgment_date")
    if conduct_date or judgment_date:
        divergence = _resolve_sources(fired_sources, conduct_date, judgment_date)

    if module == "conviction" and not _has_confirmed_jurisdiction_connection(snapshot):
        blockers.append({
            "code": "JURISDICTION_CONNECTION_UNCONFIRMED",
            "path": "entities.jurisdictionConnections",
            "message": "定罪研判需要至少一个 verificationStatus 为 confirmed 的管辖连接点",
        })

    status = "blocked" if blockers else ("calculated" if any(r["fired"] for r in rule_results)
                                         else "not_applicable")
    result_payload = {
        "schema_version": schema_version,
        "module": module,
        "status": status,
        "case_id": payload.get("case_id"),
        "facts_version_id": facts_version_id,
        "input_snapshot_ref": input_ref or None,
        "rules": rule_results,
        "dependency_snapshot": {
            "facts_version_id": facts_version_id,
            "rules": [{"ruleId": r["ruleId"], "ruleVersion": r["ruleVersion"],
                       "family": r["family"], "contentHash": r["contentHash"]}
                      for r in rules],
            "sources": sorted(fired_sources),
        },
        "blockers": blockers,
        "divergence": divergence,
        "human_review_required": True,
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


def _has_confirmed_jurisdiction_connection(snapshot: dict[str, Any]) -> bool:
    entities = snapshot.get("entities")
    if not isinstance(entities, dict):
        return False
    connections = entities.get("jurisdictionConnections")
    if not isinstance(connections, list):
        return False
    return any(
        isinstance(connection, dict)
        and connection.get("verificationStatus") == "confirmed"
        for connection in connections
    )


def _resolve_sources(source_ids: set[str], conduct: datetime.date | None,
                     judgment: datetime.date | None) -> list[dict[str, Any]]:
    from engine.store import connection

    if not source_ids:
        return []
    divergence: list[dict[str, Any]] = []
    with connection() as conn:
        rows = conn.execute(
            "SELECT source_id, source_key FROM engine.legal_source WHERE source_id = ANY(%s::uuid[])",
            (sorted(source_ids),),
        ).fetchall()
    for _, source_key in rows:
        resolution = registry.resolve_temporal(source_key, conduct, judgment)
        if resolution.get("divergence"):
            divergence.extend(resolution["divergence"])
        if resolution.get("coverageGap"):
            divergence.append({"code": "LEGAL_SOURCE_COVERAGE_GAP",
                               "detail": f"{source_key} 在行为/裁判时点无覆盖版本",
                               "gaps": resolution.get("gaps", [])})
    return divergence


class ComplianceRunner:
    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return analyze(payload, "compliance.analyze")


class ConvictionRunner:
    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return analyze(payload, "conviction.analyze")
