"""sentencing.v2 注册表化量刑单测（registry 打桩）。"""
from __future__ import annotations

import pytest

from engine.adapters import sentencing_v2
from engine.adapters.module_analysis import ModuleAnalysisError
from engine.adapters.sentencing_v2 import calculate_v2


@pytest.fixture(autouse=True)
def _stub_source_lookup(monkeypatch):
    monkeypatch.setattr(sentencing_v2.legal_temporal, "resolve_sources",
                        lambda source_ids, *_: {
                            "divergence": [], "blockers": [], "resolutions": {},
                            "source_versions": [
                                {"sourceId": source_id, "sourceVersion": "v1", "point": "as_of"}
                                for source_id in sorted(source_ids)
                            ],
                        })

RULE = {
    "rulePackageId": "rp-s1", "ruleId": "rule-sentencing-x", "ruleVersion": "1.0.0",
    "sourceIds": ["s1"], "contentHash": "hh",
    "predicate": {"path": "facts.charge.value", "op": "eq", "value": "assist"},
    "outcome": {
        "calculation": {
            "base_tiers": [
                {"when": {"path": "amounts.inflow.confirmedSum", "op": "gte", "value": 300000},
                 "months": 18},
                {"when": {"path": "amounts.settlement.confirmedSum", "op": "gte", "value": 200000},
                 "months": 12},
            ],
            "adjustments": [
                {"id": "surrender",
                 "when": {"path": "facts.has_surrender.value", "op": "eq", "value": True},
                 "direction": "decrease", "operation": "percent_of_base",
                 "value": "0.30", "source_ids": []},
                {"id": "fixed_extra",
                 "direction": "increase", "operation": "fixed_months",
                 "value": "2", "source_ids": []},
            ],
            "maximum_months": 36,
        }
    },
}

SNAPSHOT = {
    "items": [
        {"key": "charge", "value": "assist", "verificationStatus": "confirmed"},
        {"key": "has_surrender", "value": True, "verificationStatus": "confirmed"},
    ],
    "entities": {"amounts": [
        {"kind": "inflow", "value": "350000", "verificationStatus": "confirmed"},
    ]},
}


def _payload():
    return {"case_id": "c1", "input_snapshot_ref": "facts_version:fv-7",
            "metadata": {"taskType": "sentencing.calculate", "asOfDate": "2026-01-01", "factsSnapshot": SNAPSHOT,
                         "artifactVersions": {"conviction": "cv-3"}}}


def test_calculated_with_steps_and_clamp(monkeypatch):
    monkeypatch.setattr(sentencing_v2.registry, "active_rules", lambda fam, *_: [RULE])
    out = calculate_v2(_payload())
    body = out["final_output"]
    assert body["schema_version"] == "sentencing.v2"
    assert body["status"] == "calculated"
    r = body["results"][0]
    # 18 - 18*0.30 + 2 = 14.6
    assert r["term_months"] == pytest.approx(14.6)
    ops = [s["operation"] for s in r["steps"]]
    assert ops[0] == "base_tier" and "fixed_months" in ops
    assert body["human_review_required"] is True
    assert body["dependency_snapshot"]["facts_version_id"] == "fv-7"
    assert body["dependency_snapshot"]["artifacts"] == [
        {"module": "conviction", "artifactVersionId": "cv-3"}
    ]


def test_no_tier_fires_blocked(monkeypatch):
    monkeypatch.setattr(sentencing_v2.registry, "active_rules", lambda fam, *_: [RULE])
    snap = {"items": [{"key": "charge", "value": "assist", "verificationStatus": "confirmed"}],
            "entities": {"amounts": [{"kind": "inflow", "value": "100",
                                      "verificationStatus": "confirmed"}]}}
    payload = _payload()
    payload["metadata"]["factsSnapshot"] = snap
    out = calculate_v2(payload)
    body = out["final_output"]
    assert body["status"] == "blocked"
    assert body["results"][0]["blockers"][0]["code"] == "BASE_UNRESOLVED"


def test_predicate_miss_is_not_applicable(monkeypatch):
    monkeypatch.setattr(sentencing_v2.registry, "active_rules", lambda fam, *_: [RULE])
    snap = {"items": [{"key": "charge", "value": "concealment",
                        "verificationStatus": "confirmed"}], "entities": {}}
    payload = _payload()
    payload["metadata"]["factsSnapshot"] = snap
    out = calculate_v2(payload)
    assert out["final_output"]["status"] == "not_applicable"


def test_no_rules_fails_closed(monkeypatch):
    monkeypatch.setattr(sentencing_v2.registry, "active_rules", lambda fam, *_: [])
    with pytest.raises(ModuleAnalysisError) as err:
        calculate_v2(_payload())
    assert err.value.code == "MODULE_RULES_UNAVAILABLE"


def test_missing_snapshot_fails_closed():
    payload = _payload()
    payload["metadata"] = {"taskType": "sentencing.calculate"}
    with pytest.raises(ModuleAnalysisError) as err:
        calculate_v2(payload)
    assert err.value.code == "FACTS_SNAPSHOT_MISSING"


def test_missing_as_of_date_fails_closed():
    payload = _payload()
    del payload["metadata"]["asOfDate"]
    with pytest.raises(ModuleAnalysisError) as err:
        calculate_v2(payload)
    assert err.value.code == "INVALID_AS_OF_DATE"


def test_missing_confirmed_conviction_fails_closed():
    payload = _payload()
    del payload["metadata"]["artifactVersions"]
    with pytest.raises(ModuleAnalysisError) as err:
        calculate_v2(payload)
    assert err.value.code == "CONVICTION_NOT_CONFIRMED"


def test_temporal_divergence_blocks_sentence_and_outputs_both_paths(monkeypatch):
    monkeypatch.setattr(sentencing_v2.registry, "active_rules", lambda fam, *_: [RULE])
    monkeypatch.setattr(sentencing_v2.legal_temporal, "resolve_sources", lambda *_: {
        "divergence": [{"code": "LAW_VERSION_DIVERGENCE", "sourceKey": "law-x"}],
        "blockers": [], "source_versions": [], "resolutions": {},
    })
    payload = _payload()
    payload["metadata"]["factsSnapshot"] = {
        **SNAPSHOT,
        "items": [*SNAPSHOT["items"],
                  {"key": "conduct_date", "value": "2024-03-01", "verificationStatus": "confirmed"},
                  {"key": "judgment_date", "value": "2026-02-01", "verificationStatus": "confirmed"}],
    }
    body = calculate_v2(payload)["final_output"]
    assert body["status"] == "blocked"
    assert body["results"][0]["term_months"] is None
    assert len(body["temporal_paths"]) == 2
    assert {path["point"] for path in body["temporal_paths"]} == {"conduct", "judgment"}


def test_failed_temporal_paths_block_primary_even_when_outcomes_match(monkeypatch):
    broken = {**RULE, "outcome": {"calculation": {
        "base_tiers": [{"when": {"path": "amounts.inflow.confirmedSum",
                                    "op": "gte", "value": 999999}, "months": 6}],
    }}}

    def dated_rules(_family, as_of):
        return [RULE] if str(as_of) == "2025-01-01" else [broken]

    monkeypatch.setattr(sentencing_v2.registry, "active_rules", dated_rules)
    payload = _payload()
    payload["metadata"]["asOfDate"] = "2025-01-01"
    payload["metadata"]["factsSnapshot"] = {
        **SNAPSHOT,
        "items": [*SNAPSHOT["items"],
                  {"key": "conduct_date", "value": "2024-03-01", "verificationStatus": "confirmed"},
                  {"key": "judgment_date", "value": "2026-02-01", "verificationStatus": "confirmed"}],
    }
    body = calculate_v2(payload)["final_output"]
    assert body["status"] == "blocked"
    assert body["results"][0]["term_months"] is None
    path_blockers = [item for item in body["blockers"]
                     if item["code"] == "TEMPORAL_PATH_BLOCKED"]
    assert {item["point"] for item in path_blockers} == {"conduct", "judgment"}
    assert all(any(detail["code"] == "BASE_UNRESOLVED"
                   for detail in item["blockers"])
               for item in path_blockers)
    assert body["results"][0]["fine"] is None
    assert all(any(item["code"] == "BASE_UNRESOLVED" for item in path["blockers"])
               for path in body["temporal_paths"])
