"""把 legal-source 语料 JSON 播种进注册表（幂等：source_key+source_version 已存在则跳过）。

用法：
    python -m engine.rules.seed engine/adapters/legal_sources.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from engine.rules.registry import RegistryError, register_legal_source


def seed_corpus(path: str | Path) -> dict[str, int]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    sources = data.get("sources", data if isinstance(data, list) else [])
    stats = {"registered": 0, "skipped": 0, "failed": 0}
    for item in sources:
        payload = _map_source(item)
        try:
            register_legal_source(payload)
            stats["registered"] += 1
        except RegistryError as exc:
            if exc.code == "LEGAL_SOURCE_EXISTS":
                stats["skipped"] += 1
            else:
                stats["failed"] += 1
    return stats


# 语料中的细粒度文种 → 注册表 authority 封闭集（冲突优先级层级）。
# 意见/纪要/量刑指导均为司法解释性质文件，优先级归入 policy 层。
_AUTHORITY_MAP = {
    "normative_opinion": "policy",
    "sentencing_guidance": "policy",
    "meeting_minutes": "policy",
}


def _map_source(item: dict[str, Any]) -> dict[str, Any]:
    coverage = dict(item.get("coverage") or {})
    original_authority = item.get("authority")
    if original_authority in _AUTHORITY_MAP:
        coverage.setdefault("originalAuthority", original_authority)
    return {
        "source_key": item["id"],
        "title": item["title"],
        "document_number": item.get("document_number"),
        "article": item.get("article"),
        "jurisdiction": item.get("jurisdiction", "CN"),
        "authority": _AUTHORITY_MAP.get(item.get("authority"), item.get("authority", "law")),
        "source_version": item.get("source_version", "unversioned"),
        "effective_from": item["effective_from"],
        "effective_to": item.get("effective_to"),
        "official_url": item.get("official_url"),
        "excerpt": item.get("excerpt"),
        "aliases": item.get("aliases") or [],
        "verification_level": item.get("verification_level", "pending"),
        "coverage": coverage,
        "provenance": item.get("provenance") or "corpus-json",
    }


def seed_rules(path: str | Path) -> dict[str, int]:
    """播种规则语料：source_refs 用 "source_key@source_version" 引用法源，
    加载时解析为库内 source_id（跨环境可移植，不绑实例 uuid）。"""
    from engine.rules.registry import register_rule_package
    from engine.store import connection

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rules = data.get("rules", data if isinstance(data, list) else [])
    stats = {"registered": 0, "skipped": 0, "failed": 0}
    for item in rules:
        refs = item.pop("source_refs", None) or []
        ids: list[str] = []
        with connection() as conn:
            for ref in refs:
                key, _, version = ref.partition("@")
                row = conn.execute(
                    "SELECT source_id FROM engine.legal_source"
                    " WHERE source_key = %s AND source_version = %s",
                    (key, version or None),
                ).fetchone()
                if row is None:
                    row = conn.execute(
                        "SELECT source_id FROM engine.legal_source WHERE source_key = %s"
                        " ORDER BY effective_from DESC LIMIT 1", (key,),
                    ).fetchone()
                if row is None:
                    break
                ids.append(str(row[0]))
        if len(ids) != len(refs):
            stats["failed"] += 1
            continue
        item["source_ids"] = ids
        try:
            register_rule_package(item)
            stats["registered"] += 1
        except RegistryError as exc:
            if exc.code == "RULE_PACKAGE_EXISTS":
                stats["skipped"] += 1
            else:
                stats["failed"] += 1
    return stats


def seed_templates(path: str | Path) -> dict[str, int]:
    """播种模板语料：templates[] 逐条 register_template，已存在则跳过。"""
    from engine.rules.registry import register_template

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    templates = data.get("templates", data if isinstance(data, list) else [])
    stats = {"registered": 0, "skipped": 0, "failed": 0}
    for item in templates:
        try:
            register_template(item)
            stats["registered"] += 1
        except RegistryError as exc:
            if exc.code == "TEMPLATE_EXISTS":
                stats["skipped"] += 1
            else:
                stats["failed"] += 1
    return stats


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--rules":
        print(json.dumps(seed_rules(sys.argv[2]), ensure_ascii=False))
    elif len(sys.argv) > 1 and sys.argv[1] == "--templates":
        print(json.dumps(seed_templates(sys.argv[2]), ensure_ascii=False))
    else:
        target = sys.argv[1] if len(sys.argv) > 1 else "engine/adapters/legal_sources.json"
        print(json.dumps(seed_corpus(target), ensure_ascii=False))
