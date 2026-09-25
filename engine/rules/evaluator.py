"""规则谓词求值器：在 FactsVersion 快照的规范化视图上求值 JSON 谓词。

DSL（冻结为 case.rule-predicate.v1）：
    {"all": [cond...]}  {"any": [cond...]}  {"not": cond}  cond
    cond = {"path": <寻址>, "op": <操作符>, "value": <字面量>}
操作符：exists / missing / eq / neq / gt / gte / lt / lte / in / contains / confirmed

寻址约定（规范化视图）：
    facts.<key>            → fact item（按 key）
    facts.<key>.<field>    → item 字段（value/attributes.verificationStatus/...）
    amounts.<kind>.sum     → 该 kind 金额 value 合计（数值型）
    amounts.<kind>.count   → 该 kind 金额条数
    entities.<section>.count → entities.<section> 条数
    entities.<section>[<field>=<value>] 暂未支持（用 facts.* 表达）

求值返回 (fired, trace)——trace 记录每个条件的实际取值，供审计复核。
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

_OPS = ("exists", "missing", "eq", "neq", "gt", "gte", "lt", "lte", "in", "contains", "confirmed")


class PredicateError(ValueError):
    def __init__(self, message: str):
        super().__init__(message)
        self.code = "PREDICATE_INVALID"


def build_view(snapshot: dict[str, Any]) -> dict[str, Any]:
    """把 FactsVersion payload 规范化为谓词寻址视图。"""
    view: dict[str, Any] = {"facts": {}, "amounts": {}, "entities": {}}
    for item in snapshot.get("items") or []:
        if isinstance(item, dict) and item.get("key"):
            view["facts"][str(item["key"])] = item
    entities = snapshot.get("entities") or {}
    for section, rows in entities.items():
        rows = [r for r in (rows or []) if isinstance(r, dict)]
        view["entities"][section] = {"count": len(rows), "items": rows}
    amounts: dict[str, dict[str, Any]] = {}
    for row in (entities.get("amounts") or []):
        if not isinstance(row, dict):
            continue
        kind = str(row.get("kind") or "unknown")
        bucket = amounts.setdefault(kind, {"sum": Decimal(0), "count": 0,
                                           "confirmed_sum": Decimal(0), "confirmed_count": 0})
        bucket["count"] += 1
        value = row.get("value")
        try:
            numeric = Decimal(str(value)) if value is not None else None
        except (InvalidOperation, ValueError):
            numeric = None
        if numeric is not None:
            bucket["sum"] += numeric
            if row.get("verificationStatus") == "confirmed":
                bucket["confirmed_sum"] += numeric
        if row.get("verificationStatus") == "confirmed":
            bucket["confirmed_count"] += 1
    for kind, bucket in amounts.items():
        view["amounts"][kind] = {
            "sum": float(bucket["sum"]), "count": bucket["count"],
            "confirmedSum": float(bucket["confirmed_sum"]),
            "confirmedCount": bucket["confirmed_count"],
            "items": [r for r in entities.get("amounts") or []
                      if isinstance(r, dict) and str(r.get("kind")) == kind],
        }
    return view


def _resolve(view: dict[str, Any], path: str) -> tuple[bool, Any]:
    """按点路径解析；返回 (found, value)。数组段用 items 展开。"""
    node: Any = view
    for segment in path.split("."):
        if isinstance(node, dict):
            if segment not in node:
                return False, None
            node = node[segment]
        elif isinstance(node, list):
            try:
                node = node[int(segment)]
            except (ValueError, IndexError):
                return False, None
        else:
            return False, None
    return True, node


def _eq_value(actual: Any, expected: Any) -> bool:
    """事实值在库中是文本；规则字面量按类型归一后比较，不静默改语义。"""
    if isinstance(expected, bool) and isinstance(actual, str):
        lowered = actual.strip().lower()
        if lowered in ("true", "false"):
            return (lowered == "true") == expected
        return False
    if isinstance(expected, (int, float, Decimal)) and not isinstance(expected, bool) \
            and isinstance(actual, str):
        try:
            return Decimal(actual.strip()) == Decimal(str(expected))
        except (InvalidOperation, ValueError):
            return False
    return actual == expected


def _compare(op: str, found: bool, actual: Any, expected: Any) -> bool:
    if op == "exists":
        return found
    if op == "missing":
        return not found
    if not found:
        return False
    if op == "confirmed":
        return isinstance(actual, dict) and actual.get("verificationStatus") == "confirmed" \
            or actual == "confirmed"
    if op == "eq":
        return _eq_value(actual, expected)
    if op == "neq":
        return not _eq_value(actual, expected)
    if op == "in":
        return isinstance(expected, list) and actual in expected
    if op == "contains":
        if isinstance(actual, (list, str)):
            return expected in actual
        return False
    if op in ("gt", "gte", "lt", "lte"):
        try:
            left, right = Decimal(str(actual)), Decimal(str(expected))
        except (InvalidOperation, ValueError):
            return False
        return {"gt": left > right, "gte": left >= right,
                "lt": left < right, "lte": left <= right}[op]
    raise PredicateError(f"unsupported op {op}")


def evaluate(predicate: dict[str, Any], view: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
    """求值谓词，返回 (fired, trace)。trace 列出每个叶条件的解析值。"""
    trace: list[dict[str, Any]] = []

    def walk(node: Any) -> bool:
        if not isinstance(node, dict):
            raise PredicateError(f"predicate node must be object, got {type(node).__name__}")
        if "all" in node:
            children = node["all"]
            if not isinstance(children, list) or not children:
                raise PredicateError("'all' requires a non-empty list")
            return all(walk(c) for c in children)
        if "any" in node:
            children = node["any"]
            if not isinstance(children, list) or not children:
                raise PredicateError("'any' requires a non-empty list")
            return any(walk(c) for c in children)
        if "not" in node:
            return not walk(node["not"])
        path, op = node.get("path"), node.get("op", "eq")
        if not isinstance(path, str) or not path:
            raise PredicateError("condition requires 'path'")
        if op not in _OPS:
            raise PredicateError(f"unsupported op {op}")
        found, actual = _resolve(view, path)
        result = _compare(op, found, actual, node.get("value"))
        trace.append({"path": path, "op": op, "expected": node.get("value"),
                      "found": found, "actual": actual, "result": result})
        return result

    return walk(predicate), trace
