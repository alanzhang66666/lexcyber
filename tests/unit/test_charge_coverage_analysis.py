"""Adapter-level regressions for requested-charge coverage and declared paths.

These tests deliberately use synthetic, approved-shaped registry rows.  They
exercise the adapter's data-flow and fail-closed behavior without asserting
any real legal mapping or calling a real approval service.
"""
from __future__ import annotations

import copy
import datetime as dt

import pytest

from engine.adapters import module_analysis
from engine.adapters.module_analysis import ModuleAnalysisError, analyze

PROOF_A = "proof-a"
PROOF_B = "proof-b"
PROOF_J = "proof-jurisdiction"


def _path(path_id: str, charge_key: object = "charge.alpha") -> dict:
    return {
        "path_id": path_id,
        "label": f"path {path_id}",
        "charge_key": charge_key,
        "actor_fact_key": "actor_a" if path_id == "alpha" else "actor_b",
        "supporting_fact_keys": ["support_a" if path_id == "alpha" else "support_b"],
        "contrary_fact_keys": ["contrary_a" if path_id == "alpha" else "contrary_b"],
        "when_true": {"baseline_position": "candidate"},
        "when_false": {"baseline_position": "excluded", "exclusion_reason": "synthetic exclusion reason"},
    }


def _snapshot(*, dates: bool = False) -> dict:
    items = [
        {"key": "predicate_flag", "entityId": "fact-predicate", "value": True,
         "verificationStatus": "confirmed", "evidenceIds": [PROOF_A]},
        {"key": "actor_a", "entityId": "fact-actor-a", "actorId": "actor-a", "value": True,
         "verificationStatus": "confirmed", "evidenceIds": [PROOF_A]},
        {"key": "support_a", "entityId": "fact-support-a", "actorId": "actor-a", "value": True,
         "verificationStatus": "confirmed", "evidenceIds": [PROOF_A]},
        {"key": "contrary_a", "entityId": "fact-contrary-a", "actorId": "actor-a", "value": False,
         "verificationStatus": "confirmed", "evidenceIds": [PROOF_A]},
        {"key": "actor_b", "entityId": "fact-actor-b", "actorId": "actor-b", "value": True,
         "verificationStatus": "confirmed", "evidenceIds": [PROOF_B]},
        {"key": "support_b", "entityId": "fact-support-b", "actorId": "actor-b", "value": True,
         "verificationStatus": "confirmed", "evidenceIds": [PROOF_B]},
        {"key": "contrary_b", "entityId": "fact-contrary-b", "actorId": "actor-b", "value": False,
         "verificationStatus": "confirmed", "evidenceIds": [PROOF_B]},
    ]
    if dates:
        items.extend([
            {"key": "conduct_date", "entityId": "fact-conduct", "value": "2024-03-01",
             "verificationStatus": "confirmed", "evidenceIds": [PROOF_A]},
            {"key": "judgment_date", "entityId": "fact-judgment", "value": "2026-02-01",
             "verificationStatus": "confirmed", "evidenceIds": [PROOF_B]},
        ])
    return {
        "items": items,
        "entities": {
            "actors": [{"entityId": "actor-a"}, {"entityId": "actor-b"}],
            "jurisdictionConnections": [{"entityId": "jurisdiction-1",
                                          "verificationStatus": "confirmed",
                                          "evidenceIds": [PROOF_J]}],
            "evidence": [
                {"entityId": PROOF_A, "verificationStatus": "confirmed"},
                {"entityId": PROOF_B, "verificationStatus": "confirmed"},
                {"entityId": PROOF_J, "verificationStatus": "confirmed"},
            ],
        },
    }


def _rule(rule_id: str = "approved-plan", *, coverage: object = None,
          outcome: object = None, predicate: dict | None = None,
          source: str = "source-approved") -> dict:
    if coverage is None:
        coverage = {"covers": ["charge.alpha", "charge.beta"]}
    if outcome is None:
        outcome = {"candidate_paths": [_path("alpha"), _path("beta", "charge.beta")]}
    return {
        "rulePackageId": f"package-{rule_id}", "ruleId": rule_id, "ruleVersion": "1.0.0",
        "sourceIds": [source],
        "predicate": predicate or {"path": "facts.predicate_flag.value", "op": "eq", "value": True},
        "outcome": outcome, "requiredEvidenceKinds": [], "coverage": coverage,
        "contentHash": f"hash-{rule_id}",
    }


def _base_payload(*, dates: bool = False, requested: object = None,
                  include_requested: bool = False) -> dict:
    metadata = {"taskType": "conviction.analyze", "asOfDate": "2026-01-01",
                "factsSnapshot": _snapshot(dates=dates)}
    if include_requested:
        metadata["requestedCharges"] = requested
    return {"case_id": "case-coverage", "input_snapshot_ref": "facts_version:fv-coverage",
            "metadata": metadata}


def _empty_temporal(source_ids, conduct, judgment):
    point = "conduct" if conduct else "judgment" if judgment else "as_of"
    return {
        "divergence": [], "blockers": [],
        "source_versions": [{"sourceId": str(source), "sourceVersion": "1.0.0", "point": point}
                             for source in sorted(source_ids)],
        "resolutions": {},
    }


def _patch_registry(monkeypatch, rules_by_date, resolver_calls=None):
    def active_rules(family, as_of):
        if family == "distinction":
            return [dict(_rule("distinction-base", coverage={"covers": []}, outcome={"conclusion": "synthetic"},
                               source="source-distinction"))]
        date = as_of.isoformat() if hasattr(as_of, "isoformat") else str(as_of)
        return copy.deepcopy(rules_by_date.get(date, []))

    def resolve(source_ids, conduct, judgment):
        if resolver_calls is not None:
            resolver_calls.append((set(source_ids), conduct, judgment))
        return _empty_temporal(source_ids, conduct, judgment)

    monkeypatch.setattr(module_analysis.registry, "active_rules", active_rules)
    monkeypatch.setattr(module_analysis, "_resolve_sources", resolve)


def _body(monkeypatch, *, payload, rules_by_date, resolver_calls=None):
    _patch_registry(monkeypatch, rules_by_date, resolver_calls)
    return analyze(payload, "conviction.analyze")["final_output"]


def test_partial_requested_charges_preserve_raw_text_and_do_not_auto_match(monkeypatch):
    payload = _base_payload(requested=[
        {"requestedCharge": "  原始罪名文本  "},
        {"requestedCharge": "已知罪名", "chargeKey": "charge.alpha"},
        {"requestedCharge": "未知罪名", "chargeKey": "charge.unknown"},
    ], include_requested=True)
    body = _body(monkeypatch, payload=payload,
                 rules_by_date={"2026-01-01": [_rule()]})
    assert body["requested_charges"] == payload["metadata"]["requestedCharges"]
    raw_check = next(item for item in body["charge_coverage"] if item["requested_charge"] == "  原始罪名文本  ")
    assert raw_check["charge_key"] is None and raw_check["covered"] is False
    assert any(item["requested_charge"] == "  原始罪名文本  " and item["charge_key"] is None
               for item in body["missing_items"])
    assert any(item["requested_charge"] == "未知罪名" and item["charge_key"] == "charge.unknown"
               for item in body["missing_items"])
    assert not any(path["charge_key"] == "charge.unknown" for path in body["candidate_paths"])
    assert body["status"] == "blocked"


def test_plan_outside_approved_coverage_is_not_published(monkeypatch):
    rule = _rule(coverage={"covers": ["charge.alpha"]},
                 outcome={"candidate_paths": [_path("alpha"), _path("beta", "charge.not-covered")]})
    body = _body(monkeypatch, payload=_base_payload(), rules_by_date={"2026-01-01": [rule]})
    assert not any(path["charge_key"] == "charge.not-covered" for path in body["candidate_paths"])
    assert any(item["kind"] == "charge_out_of_coverage" and item["charge_key"] == "charge.not-covered"
               for item in body["missing_items"])
    assert any(item["code"] == "CHARGE_OUT_OF_COVERAGE" for item in body["blockers"])


def test_nonfiring_approved_coverage_rule_still_enters_dependencies(monkeypatch):
    false_rule = _rule("coverage-only", coverage={"covers": ["charge.gamma"]},
                       outcome={"conclusion": "synthetic"},
                       predicate={"path": "facts.predicate_flag.value", "op": "eq", "value": False},
                       source="source-coverage-only")
    plan_rule = _rule()
    calls = []
    body = _body(monkeypatch, payload=_base_payload(requested=[{"requestedCharge": "Gamma", "chargeKey": "charge.gamma"}], include_requested=True),
                 rules_by_date={"2026-01-01": [plan_rule, false_rule]}, resolver_calls=calls)
    assert body["status"] == "calculated"
    assert "source-coverage-only" in body["dependency_snapshot"]["sources"]
    assert any("source-coverage-only" in sources and conduct is None and judgment is None
               for sources, conduct, judgment in calls)
    assert any(item["sourceId"] == "source-coverage-only"
               and item["point"] == "as_of"
               for item in body["dependency_snapshot"]["source_versions"])


@pytest.mark.parametrize("coverage,charge_key", [
    ({}, ["charge.alpha"]), ({"covers": None}, ["charge.alpha"]),
    ({"covers": {}}, ["charge.alpha"]), ({"covers": 7}, ["charge.alpha"]),
    ({"covers": "charge.alpha"}, ["charge.alpha"]),
])
def test_malformed_coverage_and_plan_charge_are_controlled_blockers(monkeypatch, coverage, charge_key):
    rule = _rule(coverage=coverage, outcome={"candidate_paths": [_path("alpha", charge_key)]})
    body = _body(monkeypatch, payload=_base_payload(), rules_by_date={"2026-01-01": [rule]})
    assert body["status"] == "blocked"
    assert any(item["code"] == "CHARGE_OUT_OF_COVERAGE" for item in body["blockers"])


def test_temporal_coverage_difference_checks_dependencies_and_clears_blocked_positions(monkeypatch):
    asof = _rule("asof", coverage={"covers": ["charge.alpha", "charge.beta"]}, source="source-asof")
    conduct = _rule("conduct", coverage={"covers": ["charge.alpha", "charge.beta"]}, source="source-conduct")
    judgment = _rule("judgment", coverage={"covers": ["charge.other"]}, source="source-judgment")
    calls = []
    body = _body(monkeypatch, payload=_base_payload(dates=True, requested=[
        {"requestedCharge": "Alpha", "chargeKey": "charge.alpha"},
        {"requestedCharge": "Beta", "chargeKey": "charge.beta"},
    ], include_requested=True), rules_by_date={
        "2026-01-01": [asof], "2024-03-01": [conduct], "2026-02-01": [judgment],
    }, resolver_calls=calls)
    assert body["status"] == "blocked"
    points = {check["point"] for check in body["charge_coverage"]}
    assert {"as_of", "conduct", "judgment"}.issubset(points)
    judgment_missing = [item for item in body["missing_items"] if item["point"] == "judgment"]
    assert {item["charge_key"] for item in judgment_missing} == {"charge.alpha", "charge.beta"}
    assert {"source-asof", "source-conduct", "source-judgment"}.issubset(body["dependency_snapshot"]["sources"])
    assert any(conduct_date == dt.date(2024, 3, 1) and judgment_date is None for _, conduct_date, judgment_date in calls)
    assert any(conduct_date is None and judgment_date == dt.date(2026, 2, 1) for _, conduct_date, judgment_date in calls)
    for path in body["candidate_paths"]:
        assert path["baseline_position"] is None
        assert path["exclusion_reason"] is None


@pytest.mark.parametrize("requested", [
    [],
    [{"requestedCharge": "Other", "chargeKey": "charge.other"}],
])
def test_temporal_false_no_plan_coverage_reaches_resolver_and_source_versions(monkeypatch, requested):
    plan_rule = _rule("plan-x", coverage={"covers": []},
                      outcome={"candidate_paths": [_path("alpha", "charge.x"),
                                                    _path("beta", "charge.x")]},
                      source="source-plan")
    false_rule = _rule("temporal-false-no-plan", coverage={"covers": ["charge.x"]},
                       outcome={"conclusion": "synthetic"},
                       predicate={"path": "facts.predicate_flag.value", "op": "eq", "value": False},
                       source="source-temporal-false")
    calls = []
    body = _body(monkeypatch, payload=_base_payload(dates=True, requested=requested, include_requested=True),
                 rules_by_date={
        "2026-01-01": [plan_rule, false_rule],
        "2024-03-01": [plan_rule, false_rule],
        "2026-02-01": [plan_rule, false_rule],
    }, resolver_calls=calls)
    assert body["status"] == ("calculated" if not requested else "blocked")
    assert any("source-temporal-false" in sources
               and conduct == dt.date(2024, 3, 1) and judgment is None
               for sources, conduct, judgment in calls)
    assert any("source-temporal-false" in sources
               and conduct is None and judgment == dt.date(2026, 2, 1)
               for sources, conduct, judgment in calls)
    temporal_versions = [item for item in body["dependency_snapshot"]["source_versions"]
                         if item["sourceId"] == "source-temporal-false"]
    assert {item["point"] for item in temporal_versions} == {"conduct", "judgment"}


@pytest.mark.parametrize("requested", [
    [{"requestedCharge": "same-name"}, {"requestedCharge": "same-name", "chargeKey": "charge.alpha"}],
    [{"requestedCharge": "same-name", "chargeKey": "charge.alpha"}, {"requestedCharge": "same-name"}],
])
def test_raw_name_and_keyed_charge_permutations_preserve_input_order(monkeypatch, requested):
    payload = _base_payload(requested=requested, include_requested=True)
    body = _body(monkeypatch, payload=payload, rules_by_date={"2026-01-01": [_rule()]})
    assert body["requested_charges"] == requested
    assert [item["requested_charge"] for item in body["charge_coverage"]] == [
        item["requestedCharge"] for item in requested
    ]
    raw = next(item for item in body["charge_coverage"] if item["charge_key"] is None)
    assert raw["charge_key"] is None and raw["covered"] is False


def test_whitespace_charge_key_is_preserved_without_normalized_match(monkeypatch):
    requested = [{"requestedCharge": "Alpha", "chargeKey": "  charge.alpha  "}]
    body = _body(monkeypatch, payload=_base_payload(requested=requested, include_requested=True),
                 rules_by_date={"2026-01-01": [_rule()]})
    check = body["charge_coverage"][0]
    assert check["requested_charge"] == "Alpha"
    assert check["charge_key"] == "  charge.alpha  "
    assert check["covered"] is False
    assert body["missing_items"][0]["requested_charge"] == "Alpha"
    assert body["missing_items"][0]["charge_key"] == "  charge.alpha  "


@pytest.mark.parametrize("date_key", ["conduct_date", "judgment_date"])
def test_single_known_temporal_point_reports_missing_coverage(monkeypatch, date_key):
    payload = _base_payload(dates=False)
    payload["metadata"]["requestedCharges"] = [{"requestedCharge": "Alpha", "chargeKey": "charge.alpha"}]
    payload["metadata"]["factsSnapshot"] = _snapshot(dates=False)
    payload["metadata"]["factsSnapshot"]["items"].append({
        "key": date_key, "entityId": f"fact-{date_key}",
        "value": "2024-03-01" if date_key == "conduct_date" else "2026-02-01",
        "verificationStatus": "confirmed", "evidenceIds": [PROOF_A],
    })
    point_rule = _rule("point-no-coverage", coverage={"covers": []}, outcome={"conclusion": "synthetic"})
    point_date = "2024-03-01" if date_key == "conduct_date" else "2026-02-01"
    body = _body(monkeypatch, payload=payload, rules_by_date={
        "2026-01-01": [_rule()], point_date: [point_rule],
    })
    assert body["status"] == "blocked"
    point = "conduct" if date_key == "conduct_date" else "judgment"
    assert any(item["point"] == point and item["code"] == "CHARGE_OUT_OF_COVERAGE"
               for item in body["blockers"])


def test_only_effective_approved_rows_can_cover_requested_charge(monkeypatch):
    # The adapter sees only the registry's effective result.  Pending and
    # superseded rows are intentionally absent and cannot create coverage.
    rule = _rule(coverage={"covers": ["charge.alpha"]})
    body = _body(monkeypatch, payload=_base_payload(requested=[{"requestedCharge": "Alpha", "chargeKey": "charge.pending"}], include_requested=True),
                 rules_by_date={"2026-01-01": [rule]})
    assert body["status"] == "blocked"
    assert any(item["charge_key"] == "charge.pending" for item in body["missing_items"])
    check = next(item for item in body["charge_coverage"] if item["charge_key"] == "charge.pending")
    assert check["rule_versions"] == []


@pytest.mark.parametrize("raw", [None, {}, 1, "charge.alpha"])
def test_invalid_requested_charges_are_controlled(raw, monkeypatch):
    payload = _base_payload(requested=raw, include_requested=True)
    if raw is None:
        with pytest.raises(ModuleAnalysisError) as error:
            analyze(payload, "conviction.analyze")
        assert error.value.code == "INVALID_REQUESTED_CHARGES"
    else:
        with pytest.raises(ModuleAnalysisError) as error:
            analyze(payload, "conviction.analyze")
        assert error.value.code == "INVALID_REQUESTED_CHARGES"


@pytest.mark.parametrize("raw", [[], [{"requestedCharge": "Alpha", "chargeKey": "charge.alpha"},
                                      {"requestedCharge": "Alpha", "chargeKey": "charge.alpha"}],
                                  [{"requestedCharge": "Alpha", "chargeKey": ["charge.alpha"]}]])
def test_empty_or_duplicate_or_malformed_requested_charge_inputs(raw, monkeypatch):
    payload = _base_payload(requested=raw, include_requested=True)
    if raw == []:
        body = _body(monkeypatch, payload=payload, rules_by_date={"2026-01-01": [_rule()]})
        assert body["requested_charges"] == []
    else:
        with pytest.raises(ModuleAnalysisError) as error:
            analyze(payload, "conviction.analyze")
        assert error.value.code == "INVALID_REQUESTED_CHARGES"


def test_requested_charges_are_invalid_for_other_module(monkeypatch):
    payload = _base_payload(requested=[{"requestedCharge": "Alpha", "chargeKey": "charge.alpha"}], include_requested=True)
    with pytest.raises(ModuleAnalysisError) as error:
        analyze(payload, "compliance.analyze")
    assert error.value.code == "INVALID_REQUESTED_CHARGES"
