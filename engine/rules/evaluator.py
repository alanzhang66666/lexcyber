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


class AmountAggregationError(ValueError):
    """Facts snapshot amount component graph cannot be aggregated safely."""

    def __init__(self, message: str):
        super().__init__(message)
        self.code = "AMOUNT_AGGREGATION_INVALID"


def build_view(snapshot: dict[str, Any]) -> dict[str, Any]:
    """把 FactsVersion payload 规范化为谓词寻址视图。"""
    view: dict[str, Any] = {"facts": {}, "amounts": {}, "entities": {},
                            "_input_rows": {"amounts": {}},
                            "_input_invalid": {"amounts": {}}}
    for item in snapshot.get("items") or []:
        if isinstance(item, dict) and item.get("key"):
            view["facts"][str(item["key"])] = item
    entities = snapshot.get("entities") or {}
    for section, rows in entities.items():
        rows = [r for r in (rows or []) if isinstance(r, dict)]
        view["entities"][section] = {"count": len(rows), "items": rows}
    amount_rows = [row for row in (entities.get("amounts") or [])
                   if isinstance(row, dict)]
    # entityId is the canonical snapshot identity.  ``id`` is retained as a
    # compatibility alias because pure in-memory callers historically used it.
    amount_ids: dict[str, int] = {}
    parent_by_index: dict[int, int] = {}
    for index, row in enumerate(amount_rows):
        aliases = [row.get("entityId"), row.get("id")]
        for raw_alias in aliases:
            if raw_alias is None:
                continue
            alias = str(raw_alias)
            if not alias:
                raise AmountAggregationError("amount identity must not be empty")
            if alias in amount_ids and amount_ids[alias] != index:
                raise AmountAggregationError(f"duplicate amount identity {alias}")
            amount_ids[alias] = index
    for index, row in enumerate(amount_rows):
        component_of = row.get("componentOf")
        if component_of is None:
            continue
        amount_id = row.get("entityId") or row.get("id")
        if amount_id is None:
            raise AmountAggregationError("amount with componentOf requires an identity")
        parent_id = str(component_of)
        if parent_id not in amount_ids:
            raise AmountAggregationError(f"unknown amount componentOf {parent_id}")
        parent_by_index[index] = amount_ids[parent_id]

    # Validate the component graph once, before any aggregation.  A malformed
    # graph must block evaluation rather than silently double-counting.
    visited: set[int] = set()
    for index in parent_by_index:
        if index in visited:
            continue
        path: set[int] = set()
        cursor: int | None = index
        while cursor is not None and cursor in parent_by_index:
            if cursor in path:
                raise AmountAggregationError("cyclic amount componentOf graph")
            if cursor in visited:
                break
            path.add(cursor)
            cursor = parent_by_index[cursor]
        visited.update(path)

    def has_eligible_same_kind_ancestor(index: int, eligible: set[int]) -> bool:
        parent = parent_by_index.get(index)
        while parent is not None:
            if parent in eligible and amount_rows[parent].get("kind") == amount_rows[index].get("kind"):
                return True
            parent = parent_by_index.get(parent)
        return False

    amounts: dict[str, dict[str, Any]] = {}
    numeric_by_index: dict[int, Decimal] = {}
    for index, row in enumerate(amount_rows):
        value = row.get("value")
        try:
            numeric = Decimal(str(value)) if value is not None else None
        except (InvalidOperation, ValueError):
            numeric = None
        if numeric is not None and not numeric.is_finite():
            raise AmountAggregationError("amount value must be finite")
        if numeric is not None:
            numeric_by_index[index] = numeric

    eligible_by_kind: dict[str, set[int]] = {}
    confirmed_eligible_by_kind: dict[str, set[int]] = {}
    for index in numeric_by_index:
        kind = str(amount_rows[index].get("kind") or "unknown")
        eligible_by_kind.setdefault(kind, set()).add(index)
        if amount_rows[index].get("verificationStatus") == "confirmed":
            confirmed_eligible_by_kind.setdefault(kind, set()).add(index)

    for index, row in enumerate(amount_rows):
        if not isinstance(row, dict):
            continue
        kind = str(row.get("kind") or "unknown")
        bucket = amounts.setdefault(kind, {"sum": Decimal(0), "count": 0,
                                           "confirmed_sum": Decimal(0), "confirmed_count": 0})
        bucket["count"] += 1
        numeric = numeric_by_index.get(index)
        general_eligible = eligible_by_kind.get(kind, set())
        confirmed_eligible = confirmed_eligible_by_kind.get(kind, set())
        if numeric is not None and not has_eligible_same_kind_ancestor(index, general_eligible):
            bucket["sum"] += numeric
        if (numeric is not None and row.get("verificationStatus") == "confirmed"
                and not has_eligible_same_kind_ancestor(index, confirmed_eligible)):
            bucket["confirmed_sum"] += numeric
        if row.get("verificationStatus") == "confirmed":
            bucket["confirmed_count"] += 1
    for kind, bucket in amounts.items():
        rows_for_kind = [r for r in amount_rows if str(r.get("kind") or "unknown") == kind]
        sum_rows = [amount_rows[i] for i in sorted(eligible_by_kind.get(kind, set()))
                    if not has_eligible_same_kind_ancestor(i, eligible_by_kind.get(kind, set()))]
        confirmed_sum_rows = [amount_rows[i] for i in sorted(confirmed_eligible_by_kind.get(kind, set()))
                              if not has_eligible_same_kind_ancestor(
                                  i, confirmed_eligible_by_kind.get(kind, set()))]
        confirmed_rows = [r for r in rows_for_kind if r.get("verificationStatus") == "confirmed"]
        invalid_sum_rows = [amount_rows[i] for i, row in enumerate(amount_rows)
                            if str(row.get("kind") or "unknown") == kind
                            and i not in numeric_by_index
                            and not has_eligible_same_kind_ancestor(i, eligible_by_kind.get(kind, set()))]
        invalid_confirmed_rows = [amount_rows[i] for i, row in enumerate(amount_rows)
                                  if str(row.get("kind") or "unknown") == kind
                                  and row.get("verificationStatus") == "confirmed"
                                  and i not in numeric_by_index
                                  and not has_eligible_same_kind_ancestor(
                                      i, confirmed_eligible_by_kind.get(kind, set()))]
        input_rows = {"sum": sum_rows, "confirmedSum": confirmed_sum_rows,
                      "count": rows_for_kind, "confirmedCount": confirmed_rows}
        input_invalid = {"sum": invalid_sum_rows, "confirmedSum": invalid_confirmed_rows,
                         "count": [], "confirmedCount": []}
        view["_input_rows"]["amounts"][kind] = input_rows
        view["_input_invalid"]["amounts"][kind] = input_invalid
        self_rows, non_self_rows = _ownership_rows(confirmed_sum_rows)
        input_rows["confirmedSumSelf"] = self_rows
        input_rows["confirmedSumNonSelf"] = non_self_rows
        input_invalid["confirmedSumSelf"] = []
        input_invalid["confirmedSumNonSelf"] = []
        view["amounts"][kind] = {
            "sum": float(bucket["sum"]), "count": bucket["count"],
            "confirmedSum": float(bucket["confirmed_sum"]),
            "confirmedCount": bucket["confirmed_count"],
            "confirmedSumSelf": _amount_total(self_rows),
            "confirmedSumNonSelf": _amount_total(non_self_rows),
            "items": rows_for_kind,
            "_input_rows": input_rows,
            "_input_invalid": input_invalid,
        }
    return view


def _account_ownership(row: dict[str, Any]) -> str | None:
    """Map an amount row onto the S6/S7 account sets. Unknown values stay out of both."""
    raw = row.get("accountOwnership", row.get("account_ownership"))
    if not isinstance(raw, str) or not raw.strip():
        attributes = row.get("attributes")
        if isinstance(attributes, dict):
            raw = attributes.get("accountOwnership", attributes.get("account_ownership"))
    if not isinstance(raw, str):
        return None
    key = raw.strip().lower()
    if key in {"self", "own", "self_account"}:
        return "self"
    if key in {"non_self", "nonself", "other", "unit"}:
        return "non_self"
    return None


def _ownership_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    self_rows = [row for row in rows if _account_ownership(row) == "self"]
    non_self_rows = [row for row in rows if _account_ownership(row) == "non_self"]
    return self_rows, non_self_rows


def _amount_total(rows: list[dict[str, Any]]) -> float:
    total = Decimal(0)
    for row in rows:
        total += Decimal(str(row.get("value")))
    return float(total)


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
