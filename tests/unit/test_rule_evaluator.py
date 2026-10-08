"""规则谓词求值器单测（纯内存，不需要 DB）。"""
from __future__ import annotations

import pytest

from engine.rules.evaluator import AmountAggregationError, PredicateError, build_view, evaluate

SNAPSHOT = {
    "items": [
        {"key": "upstream_crime_completed", "value": True, "verificationStatus": "confirmed"},
        {"key": "account_count", "value": 4, "verificationStatus": "confirmed"},
        {"key": "knowledge_of_crime", "value": "explicit", "verificationStatus": "candidate"},
        {"key": "conduct_date", "value": "2024-03-01", "verificationStatus": "confirmed"},
    ],
    "entities": {
        "actors": [{"type": "person", "role": "suspect", "verificationStatus": "confirmed"}],
        "amounts": [
            {"kind": "inflow", "value": "200000", "verificationStatus": "confirmed"},
            {"kind": "inflow", "value": "150000", "verificationStatus": "candidate"},
            {"kind": "settlement", "value": "80000", "verificationStatus": "confirmed"},
        ],
        "jurisdictionConnections": [],
        "events": [], "evidence": [],
    },
}


@pytest.fixture()
def view():
    return build_view(SNAPSHOT)


def test_eq_and_exists(view):
    fired, trace = evaluate(
        {"all": [{"path": "facts.upstream_crime_completed.value", "op": "eq", "value": True},
                 {"path": "facts.account_count.value", "op": "gte", "value": 3}]}, view)
    assert fired
    assert len(trace) == 2 and all(t["result"] for t in trace)


def test_missing_and_amount_aggregates(view):
    fired, _ = evaluate(
        {"all": [{"path": "facts.nonexistent_key", "op": "missing"},
                 {"path": "amounts.inflow.sum", "op": "gte", "value": 300000}]}, view)
    assert fired
    fired2, _ = evaluate(
        {"path": "amounts.inflow.confirmedSum", "op": "eq", "value": 200000}, view)
    assert fired2


def test_candidate_not_confirmed(view):
    fired, _ = evaluate(
        {"path": "facts.knowledge_of_crime", "op": "confirmed"}, view)
    assert not fired


def test_any_not_in(view):
    fired, _ = evaluate(
        {"any": [{"path": "facts.knowledge_of_crime.value", "op": "in",
                  "value": ["explicit", "presumed"]},
                 {"path": "facts.account_count.value", "op": "lt", "value": 3}]}, view)
    assert fired
    fired2, _ = evaluate(
        {"not": {"path": "facts.upstream_crime_completed.value", "op": "eq", "value": True}}, view)
    assert not fired2


def test_invalid_predicate_raises(view):
    with pytest.raises(PredicateError):
        evaluate({"path": "facts.x", "op": "bogus"}, view)
    with pytest.raises(PredicateError):
        evaluate({"all": []}, view)


def test_amount_components_are_counted_once_per_kind_and_aggregate():
    snapshot = {"entities": {"amounts": [
        {"id": "child", "kind": "payment_settlement_amount", "value": "80000",
         "verificationStatus": "confirmed", "componentOf": "parent"},
        {"id": "parent", "kind": "payment_settlement_amount", "value": "120000",
         "verificationStatus": "confirmed"},
    ]}}
    amounts = build_view(snapshot)["amounts"]["payment_settlement_amount"]
    assert amounts["sum"] == 120000
    assert amounts["confirmedSum"] == 120000
    assert amounts["count"] == 2 and amounts["confirmedCount"] == 2


def test_amount_components_resolve_canonical_entity_id_with_external_id_alias():
    parent_id = "11111111-1111-4111-8111-111111111111"
    child_id = "22222222-2222-4222-8222-222222222222"
    snapshot = {"entities": {"amounts": [
        {"entityId": child_id, "id": "child-external", "kind": "illegal_gain", "value": "20",
         "verificationStatus": "confirmed", "componentOf": parent_id},
        {"entityId": parent_id, "id": "parent-external", "kind": "illegal_gain", "value": "100",
         "verificationStatus": "confirmed"},
    ]}}
    amounts = build_view(snapshot)["amounts"]["illegal_gain"]
    assert amounts["sum"] == 100
    assert amounts["confirmedSum"] == 100


def test_amount_components_are_order_independent_and_nested():
    rows = [
        {"id": "leaf", "kind": "illegal_gain", "value": "20000",
         "verificationStatus": "confirmed", "componentOf": "middle"},
        {"id": "root", "kind": "illegal_gain", "value": "120000",
         "verificationStatus": "confirmed"},
        {"id": "middle", "kind": "illegal_gain", "value": "80000",
         "verificationStatus": "confirmed", "componentOf": "root"},
    ]
    amounts = build_view({"entities": {"amounts": rows}})["amounts"]["illegal_gain"]
    assert amounts["sum"] == 120000
    assert amounts["confirmedSum"] == 120000


def test_amount_components_keep_distinct_kind_subtotals_and_statuses():
    rows = [
        {"id": "child", "kind": "payment_settlement_amount", "value": "80000",
         "verificationStatus": "confirmed", "componentOf": "parent"},
        {"id": "parent", "kind": "crime_amount", "value": "120000",
         "verificationStatus": "candidate"},
    ]
    amounts = build_view({"entities": {"amounts": rows}})["amounts"]
    assert amounts["payment_settlement_amount"]["sum"] == 80000
    assert amounts["payment_settlement_amount"]["confirmedSum"] == 80000
    assert amounts["crime_amount"]["sum"] == 120000
    assert amounts["crime_amount"]["confirmedSum"] == 0


@pytest.mark.parametrize("parent_status,child_status,confirmed", [
    ("candidate", "confirmed", 110000),
    ("conflicted", "confirmed", 110000),
    ("confirmed", "candidate", 150000),
    ("confirmed", "conflicted", 150000),
    ("candidate", "candidate", 30000),
])
def test_confirmed_subtotal_never_absorbs_child_into_unverified_parent(parent_status, child_status, confirmed):
    rows = [
        {"id": "child", "kind": "payment_settlement_amount", "value": 80000,
         "componentOf": "parent", "verificationStatus": child_status},
        {"id": "parent", "kind": "payment_settlement_amount", "value": 120000,
         "verificationStatus": parent_status},
        {"id": "independent", "kind": "payment_settlement_amount", "value": 30000,
         "verificationStatus": "confirmed"},
    ]
    subtotal = build_view({"entities": {"amounts": rows}})["amounts"]["payment_settlement_amount"]
    assert subtotal["sum"] == 150000
    assert subtotal["confirmedSum"] == confirmed


@pytest.mark.parametrize("rows", [
    [
        {"id": "a", "kind": "illegal_gain", "value": "10", "componentOf": "b"},
        {"id": "b", "kind": "illegal_gain", "value": "20", "componentOf": "a"},
    ],
    [
        {"id": "a", "kind": "illegal_gain", "value": "10", "componentOf": "missing"},
    ],
])
def test_invalid_amount_component_graph_fails_closed(rows):
    with pytest.raises(AmountAggregationError):
        build_view({"entities": {"amounts": rows}})


def test_nonfinite_amount_fails_closed():
    with pytest.raises(AmountAggregationError):
        build_view({"entities": {"amounts": [
            {"id": "a", "kind": "illegal_gain", "value": "NaN"},
        ]}})
