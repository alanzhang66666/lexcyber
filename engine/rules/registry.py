"""法源/规则/模板注册与会签存取（v1.3 §6.1-6.4，INV-LEGAL-004..007、INV-RULE-001/002）。

持久化在 engine schema（V6）。批准/会签必须走 signoff() 同事务路径
（DB 触发器校验 engine.signoff_authorized GUC），内容版本冻结。
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from typing import Any

from psycopg import IntegrityError
from psycopg.types.json import Jsonb

from engine.store import connection

AUTHORITIES = (
    "constitution", "law", "judicial_interpretation", "department_rule",
    "local_rule", "guiding_case", "policy",
)
# INV-LEGAL-004：冲突优先级由 authority 决定，不靠生效日期新旧排序
AUTHORITY_RANK = {name: i for i, name in enumerate(AUTHORITIES)}

VERIFICATION_LEVELS = ("pending", "verified", "signed_off", "disputed", "unsupported")
REVIEW_STATUSES = ("pending", "approved", "rejected", "superseded")
FAMILIES = ("compliance", "conviction", "distinction", "sentencing")
# 模块 → 需要的规则 family 集（模块可用性 = 全部 family 都有 approved 包）
MODULE_FAMILIES = {
    "compliance": ("compliance",),
    "conviction": ("conviction", "distinction"),
    "sentencing": ("sentencing",),
}


def _canonical_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class RegistryError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _require_initial_review(item: dict[str, Any], field: str, allowed: tuple[str, ...]) -> None:
    value = item.get(field, "pending")
    if not isinstance(value, str) or value not in allowed:
        raise RegistryError("REGISTRY_REVIEW_REQUIRED",
                            f"initial {field} must be one of {allowed}; review requires signoff()")


_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_explicit_date(value: date | str | None, field: str = "asOfDate") -> date:
    """Parse a required legal-analysis date; never substitute the wall clock."""
    if isinstance(value, datetime):
        raise RegistryError("INVALID_AS_OF_DATE", f"{field} must be a date without time")
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not _ISO_DATE.fullmatch(value):
        raise RegistryError("INVALID_AS_OF_DATE", f"{field} must be an ISO date (YYYY-MM-DD)")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise RegistryError("INVALID_AS_OF_DATE", f"{field} must be a valid ISO date (YYYY-MM-DD)") from exc


def require_as_of_date(metadata: dict[str, Any]) -> date:
    return parse_explicit_date(metadata.get("asOfDate"), "metadata.asOfDate")


# ---------------------------------------------------------------------------
# 法源
# ---------------------------------------------------------------------------

def register_legal_source(item: dict[str, Any]) -> dict[str, Any]:
    """登记一个法源版本（默认 pending）。source_key+source_version 唯一。"""
    _require_initial_review(item, "verification_level", ("pending", "verified"))
    required = ("source_key", "title", "authority", "source_version", "effective_from")
    missing = [k for k in required if not item.get(k)]
    if missing:
        raise RegistryError("INVALID_LEGAL_SOURCE", f"missing fields: {missing}")
    if item["authority"] not in AUTHORITIES:
        raise RegistryError("INVALID_LEGAL_SOURCE", f"unknown authority {item['authority']}")
    content_hash = item.get("content_hash") or _canonical_hash({
        k: item.get(k) for k in (
            "source_key", "title", "document_number", "article", "jurisdiction",
            "authority", "source_version", "effective_from", "effective_to",
            "excerpt", "coverage")
    })
    with connection() as conn:
        try:
            row = conn.execute(
                """
                INSERT INTO engine.legal_source(
                    source_key, title, document_number, article, jurisdiction, authority,
                    source_version, effective_from, effective_to, repeal_date,
                    official_url, excerpt, content_hash, provenance, verification_level, coverage)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING source_id
                """,
                (
                    item["source_key"], item["title"], item.get("document_number"),
                    item.get("article"), item.get("jurisdiction", "CN"), item["authority"],
                    item["source_version"], item["effective_from"], item.get("effective_to"),
                    item.get("repeal_date"), item.get("official_url"), item.get("excerpt"),
                    content_hash, item.get("provenance"),
                    item.get("verification_level", "pending"), Jsonb(item.get("coverage") or {}),
                ),
            ).fetchone()
        except IntegrityError as exc:
            raise RegistryError("LEGAL_SOURCE_EXISTS",
                                f"{item['source_key']}@{item['source_version']} already registered") from exc
        source_id = row[0]
        for alias in item.get("aliases") or []:
            conn.execute(
                "INSERT INTO engine.legal_source_alias(source_id, alias) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                (source_id, alias),
            )
    return {"sourceId": str(source_id), "contentHash": content_hash}


def link_supersession(predecessor: str, successor: str, relation_type: str = "replaces",
                      note: str | None = None) -> None:
    """显式建新旧链（INV-LEGAL-005）。入参为 source_id（uuid 文本）。"""
    if relation_type not in ("replaces", "amends", "repeals", "partially_replaces"):
        raise RegistryError("INVALID_SUPERSESSION", f"unknown relation_type {relation_type}")
    with connection() as conn:
        conn.execute(
            "INSERT INTO engine.legal_source_supersession(predecessor_id, successor_id, relation_type, note)"
            " VALUES (%s,%s,%s,%s)",
            (predecessor, successor, relation_type, note),
        )


def resolve_temporal(source_key: str, conduct_date: date | None,
                     judgment_date: date | None) -> dict[str, Any]:
    """双时点解析（§6.2 / INV-LEGAL-006）：

    同一 source_key 的各版本按 effective_from/to 区间匹配 conduct/judgment 两个时点；
    两点落在不同版本 → divergence，阻断自动择一；任一时点无覆盖 → 覆盖缺口而非近似。
    """
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT source_id, source_key, source_version, effective_from, effective_to,
                   repeal_date, verification_level, authority, title, article,
                   document_number, jurisdiction, official_url, excerpt, provenance, coverage
            FROM engine.effective_legal_source WHERE source_key = %s ORDER BY effective_from
            """,
            (source_key,),
        ).fetchall()
    if not rows:
        return {"found": False, "coverageGap": True,
                "detail": f"no legal_source registered for {source_key}"}

    def pick(point: date | None):
        if point is None:
            return []
        return [r for r in rows
                if r[3] <= point and (r[4] is None or point <= r[4])]

    conduct = pick(conduct_date)
    judgment = pick(judgment_date)
    result: dict[str, Any] = {"found": True, "coverageGap": False,
                              "overlap": False, "divergence": []}
    point_hits = (("conduct", conduct_date, conduct), ("judgment", judgment_date, judgment))
    for label, point, hits in point_hits:
        if point is not None and not hits:
            result["coverageGap"] = True
            result.setdefault("gaps", []).append(
                {"point": label, "date": str(point), "detail": "no version covers this date"})
        if len(hits) > 1:
            result["overlap"] = True
            result.setdefault("overlaps", []).append({
                "point": label, "date": str(point),
                "candidates": [_source_view(row) for row in hits],
            })
        elif hits:
            result[f"{label}_law"] = _source_view(hits[0])
        result.setdefault("resolutions", {})[label] = {
            "date": str(point) if point is not None else None,
            "candidates": [_source_view(row) for row in hits],
        }
    if (len(conduct) == 1 and len(judgment) == 1
            and conduct[0][0] != judgment[0][0]):
        result["divergence"] = [{
            "code": "LAW_VERSION_DIVERGENCE",
            "detail": "行为时点与裁判时点落在同一法源的不同版本区间，须人工择法",
            "conductVersion": conduct[0][2], "judgmentVersion": judgment[0][2],
        }]
    if result["overlap"]:
        result["divergence"].append({
            "code": "LAW_VERSION_OVERLAP",
            "detail": "法源有效区间重叠，无法自动选择版本",
            "points": [item["point"] for item in result["overlaps"]],
        })
    return result


def _source_view(row) -> dict[str, Any]:
    return {
        "sourceId": str(row[0]), "sourceKey": row[1], "sourceVersion": row[2],
        "effectiveFrom": str(row[3]), "effectiveTo": str(row[4]) if row[4] else None,
        "repealDate": str(row[5]) if row[5] else None,
        "verificationLevel": row[6], "authority": row[7],
        "title": row[8], "article": row[9], "documentNumber": row[10],
        "jurisdiction": row[11], "officialUrl": row[12], "excerpt": row[13],
        "provenance": row[14], "coverage": row[15] or {},
    }


# ---------------------------------------------------------------------------
# 规则包 / 模板
# ---------------------------------------------------------------------------

def register_rule_package(item: dict[str, Any]) -> dict[str, Any]:
    from engine.rules.conviction_paths import validate_candidate_path_definitions

    _require_initial_review(item, "legal_review_status", ("pending",))
    required = ("rule_id", "rule_version", "family", "predicate", "outcome")
    missing = [k for k in required if item.get(k) is None]
    if missing:
        raise RegistryError("INVALID_RULE_PACKAGE", f"missing fields: {missing}")
    if item["family"] not in FAMILIES:
        raise RegistryError("INVALID_RULE_PACKAGE", f"unknown family {item['family']}")
    path_errors = validate_candidate_path_definitions(item["outcome"])
    if isinstance(item["outcome"], dict) and "candidate_paths" in item["outcome"] and item["family"] not in {"conviction", "distinction"}:
        raise RegistryError("INVALID_CONVICTION_PATH_PLAN", "candidate_paths requires conviction or distinction family")
    if path_errors:
        raise RegistryError("INVALID_CONVICTION_PATH_PLAN", str(path_errors))
    if isinstance(item["outcome"], dict) and "candidate_paths" in item["outcome"] and not item.get("source_ids"):
        raise RegistryError("INVALID_CONVICTION_PATH_PLAN", "declared paths require registered legal sources")
    content_hash = item.get("content_hash") or _canonical_hash({
        k: item.get(k) for k in ("rule_id", "rule_version", "family", "predicate",
                                 "outcome", "source_ids", "coverage", "required_evidence_kinds")
    })
    with connection() as conn:
        source_ids = item.get("source_ids") or []
        if source_ids:
            found = conn.execute(
                "SELECT COUNT(*) FROM engine.legal_source WHERE source_id = ANY(%s::uuid[])",
                ([str(s) for s in source_ids],),
            ).fetchone()[0]
            if found != len(source_ids):
                raise RegistryError("UNKNOWN_LEGAL_SOURCE",
                                    "source_ids must reference registered legal_source rows")
        try:
            row = conn.execute(
                """
                INSERT INTO engine.rule_package(
                    rule_id, rule_version, family, legal_review_status,
                    effective_from, effective_to, source_ids, predicate, outcome,
                    required_evidence_kinds, coverage, content_hash)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING rule_package_id
                """,
                (
                    item["rule_id"], item["rule_version"], item["family"],
                    item.get("legal_review_status", "pending"),
                    item.get("effective_from"), item.get("effective_to"),
                    Jsonb(source_ids), Jsonb(item["predicate"]), Jsonb(item["outcome"]),
                    Jsonb(item.get("required_evidence_kinds") or []),
                    Jsonb(item.get("coverage") or {}), content_hash,
                ),
            ).fetchone()
        except IntegrityError as exc:
            raise RegistryError("RULE_PACKAGE_EXISTS",
                                f"{item['rule_id']}@{item['rule_version']} already registered") from exc
    return {"rulePackageId": str(row[0]), "contentHash": content_hash}


def register_template(item: dict[str, Any]) -> dict[str, Any]:
    _require_initial_review(item, "legal_review_status", ("pending",))
    required = ("template_id", "template_version", "doc_type", "body_template")
    missing = [k for k in required if not item.get(k)]
    if missing:
        raise RegistryError("INVALID_TEMPLATE", f"missing fields: {missing}")
    content_hash = item.get("content_hash") or _canonical_hash({
        k: item.get(k) for k in ("template_id", "template_version", "doc_type",
                                 "field_schema", "body_template")
    })
    with connection() as conn:
        try:
            conn.execute(
                """
            INSERT INTO engine.template_package(
                template_id, template_version, doc_type, legal_review_status,
                field_schema, body_template, content_hash)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                item["template_id"], item["template_version"], item["doc_type"],
                item.get("legal_review_status", "pending"),
                Jsonb(item.get("field_schema") or {}), item["body_template"], content_hash,
            ),
            )
        except IntegrityError as exc:
            raise RegistryError("TEMPLATE_EXISTS",
                                f"{item['template_id']}@{item['template_version']} already registered") from exc
    return {"templateId": item["template_id"],
            "templateVersion": item["template_version"], "contentHash": content_hash}


# ---------------------------------------------------------------------------
# 会签（唯一批准路径：同事务 signoff_record + 状态推进；触发器校验 GUC）
# ---------------------------------------------------------------------------

_SUBJECT_TABLE = {
    "rule": ("engine.rule_package", "rule_id || '@' || rule_version", "legal_review_status"),
    "template": ("engine.template_package", "template_id || '@' || template_version", "legal_review_status"),
    "legal_source": ("engine.legal_source", "source_key || '@' || source_version", "verification_level"),
}


def signoff(subject_kind: str, subject_key: str, reviewer: str, role: str,
            decision: str, comment: str | None = None) -> dict[str, Any]:
    if subject_kind not in _SUBJECT_TABLE:
        raise RegistryError("INVALID_SIGNOFF", f"unknown subject_kind {subject_kind}")
    if decision not in ("approved", "rejected"):
        raise RegistryError("INVALID_SIGNOFF", f"unknown decision {decision}")
    if not reviewer or not role:
        raise RegistryError("INVALID_SIGNOFF", "reviewer and role are required")
    table, key_expr, status_col = _SUBJECT_TABLE[subject_kind]
    target_status = {"rule": "approved", "template": "approved",
                     "legal_source": "signed_off"}[subject_kind] if decision == "approved" \
        else {"rule": "rejected", "template": "rejected", "legal_source": "disputed"}[subject_kind]
    with connection() as conn:
        conn.execute("SELECT set_config('engine.signoff_authorized', 'on', true)")
        cur = conn.execute(
            "INSERT INTO engine.signoff_record(subject_kind, subject_key, reviewer, role, decision, comment)"
            " VALUES (%s,%s,%s,%s,%s,%s) RETURNING signoff_id",
            (subject_kind, subject_key, reviewer, role, decision, comment),
        )
        signoff_id = cur.fetchone()[0]
        updated = conn.execute(
            f"UPDATE {table} SET {status_col} = %s WHERE {key_expr} = %s",
            (target_status, subject_key),
        ).rowcount
        if updated == 0:
            raise RegistryError("SIGNOFF_TARGET_NOT_FOUND", f"no {subject_kind} matches {subject_key}")
    return {"signoffId": str(signoff_id), "subject": subject_key, "decision": decision}


# ---------------------------------------------------------------------------
# 能力声明（供 Java 派发门闩）与覆盖检查（INV-LEGAL-007）
# ---------------------------------------------------------------------------

def capabilities() -> dict[str, Any]:
    """每个模块的可用性 = 所需 family 全部存在 approved 规则包。"""
    with connection() as conn:
        rows = conn.execute(
            "SELECT family, rule_id, rule_version FROM engine.effective_rule_package"
            " WHERE legal_review_status = 'approved' ORDER BY family, rule_id"
        ).fetchall()
        templates = conn.execute(
            "SELECT template_id, template_version, doc_type FROM engine.effective_template_package"
            " WHERE legal_review_status = 'approved' ORDER BY template_id"
        ).fetchall()
        pending = conn.execute(
            "SELECT family, COUNT(*) FROM engine.rule_package"
            " WHERE legal_review_status = 'pending' GROUP BY family"
        ).fetchall()
    approved_by_family: dict[str, list[str]] = {}
    for family, rule_id, version in rows:
        approved_by_family.setdefault(family, []).append(f"{rule_id}@{version}")
    modules = {}
    for module, families in MODULE_FAMILIES.items():
        missing = [f for f in families if not approved_by_family.get(f)]
        modules[module] = {
            "available": not missing,
            "missingFamilies": missing,
            "approvedRules": {f: approved_by_family.get(f, []) for f in families},
        }
    approved_templates = [{"templateId": t[0], "templateVersion": t[1], "docType": t[2]}
                          for t in templates]
    modules["draft"] = {
        "available": bool(approved_templates),
        "approvedDocTypes": sorted({t["docType"] for t in approved_templates}),
        "missingFamilies": [],
        "approvedRules": {},
    }
    return {
        "modules": modules,
        "templates": approved_templates,
        "pendingRules": {f: n for f, n in pending},
    }


def active_template(doc_type: str) -> dict[str, Any] | None:
    """产出路径专用：某 doc_type 最新 approved 模板（INV-RULE-002）。"""
    with connection() as conn:
        row = conn.execute(
            """
            SELECT template_id, template_version, field_schema,
                   body_template, content_hash
            FROM engine.effective_template_package
            WHERE doc_type = %s AND legal_review_status = 'approved'
            ORDER BY created_at DESC LIMIT 1
            """,
            (doc_type,),
        ).fetchone()
    if row is None:
        return None
    return {
        "templateId": row[0], "templateVersion": row[1],
        "fieldSchema": row[2] or {}, "bodyTemplate": row[3], "contentHash": row[4],
    }


def active_rules(family: str, as_of: date | str | None = None) -> list[dict[str, Any]]:
    """产出路径专用：只读 approved 且在有效期内的规则包（INV-RULE-002）。"""
    if family not in FAMILIES:
        raise RegistryError("INVALID_FAMILY", f"unknown family {family}")
    as_of = parse_explicit_date(as_of)
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT rule_package_id, rule_id, rule_version, source_ids, predicate, outcome,
                   required_evidence_kinds, coverage, content_hash
            FROM engine.effective_rule_package
            WHERE family = %s AND legal_review_status = 'approved'
              AND (effective_from IS NULL OR effective_from <= %s)
              AND (effective_to IS NULL OR effective_to >= %s)
            ORDER BY rule_id
            """,
            (family, as_of, as_of),
        ).fetchall()
    return [{
        "rulePackageId": str(r[0]), "ruleId": r[1], "ruleVersion": r[2],
        "sourceIds": [str(s) for s in (r[3] or [])], "predicate": r[4],
        "outcome": r[5], "requiredEvidenceKinds": r[6] or [], "coverage": r[7] or {},
        "contentHash": r[8],
    } for r in rows]


def coverage_check(family: str, needed_keys: list[str], as_of: date | str | None = None) -> dict[str, Any]:
    """INV-LEGAL-007：覆盖边界外的查询返回明确缺口，不返回近似结果。"""
    active = active_rules(family, as_of)
    covered: set[str] = set()
    for rule in active:
        cov = rule.get("coverage") or {}
        for key in cov.get("covers", []):
            covered.add(key)
    missing = [k for k in needed_keys if k not in covered]
    return {"family": family, "covered": sorted(covered), "missing": missing,
            "complete": not missing}
