"""规则谓词求值器单测（纯内存，不需要 DB）。"""
from __future__ import annotations

import pytest

from engine.rules.evaluator import PredicateError, build_view, evaluate

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
