"""模块分析适配器单测：registry 打桩，验证 payload 形状与阻断语义。"""
from __future__ import annotations

import datetime

import pytest

from engine.adapters import module_analysis
from engine.adapters.module_analysis import ModuleAnalysisError, analyze

SNAPSHOT = {
    "items": [
        {"key": "upstream_crime_completed", "entityId": "fact-upstream", "value": True, "verificationStatus": "confirmed", "evidenceIds": ["proof-1"]},
        {"key": "conduct_date", "entityId": "fact-conduct", "value": "2024-03-01", "verificationStatus": "confirmed", "evidenceIds": ["proof-1"]},
        {"key": "judgment_date", "entityId": "fact-judgment", "value": "2026-02-01", "verificationStatus": "confirmed", "evidenceIds": ["proof-1"]},
    ],
    "entities": {"jurisdictionConnections": [{"verificationStatus": "confirmed"}],
                  "evidence": [{"entityId": "proof-1", "verificationStatus": "confirmed"}]},
}

APPROVED_RULE = {
    "rulePackageId": "rp-1", "ruleId": "rule-test", "ruleVersion": "1.0.0",
    "sourceIds": ["s1"], "predicate": {"path": "facts.upstream_crime_completed.value",
                                       "op": "eq", "value": True},
    "outcome": {"conclusion": "upstream_done"},
    "requiredEvidenceKinds": [], "coverage": {}, "contentHash": "h1",
}

EMPTY_TEMPORAL = {"divergence": [], "blockers": [], "source_versions": [],
                  "resolutions": {}}


def _payload(task_type="compliance.analyze"):
    return {"case_id": "case-1", "input_snapshot_ref": "facts_version:fv-9",
            "metadata": {"taskType": task_type, "asOfDate": "2026-01-01", "factsSnapshot": SNAPSHOT}}


def test_missing_snapshot_fails_closed(monkeypatch):
    monkeypatch.setattr(module_analysis.registry, "active_rules",
                        lambda fam: [APPROVED_RULE])
    payload = _payload()
    payload["metadata"] = {"taskType": "compliance.analyze"}
    with pytest.raises(ModuleAnalysisError) as err:
        analyze(payload, "compliance.analyze")
    assert err.value.code == "FACTS_SNAPSHOT_MISSING"


@pytest.mark.parametrize("value", [None, "2026-1-1", "2026-02-30"])
def test_missing_or_invalid_as_of_date_fails_closed(monkeypatch, value):
    monkeypatch.setattr(module_analysis.registry, "active_rules", lambda *args: pytest.fail("rules must not load"))
    payload = _payload()
    payload["metadata"]["asOfDate"] = value
    with pytest.raises(ModuleAnalysisError) as err:
        analyze(payload, "compliance.analyze")
    assert err.value.code == "INVALID_AS_OF_DATE"


def test_no_approved_rules_fails_closed(monkeypatch):
    monkeypatch.setattr(module_analysis.registry, "active_rules", lambda fam, *_: [])
    body = analyze(_payload(), "compliance.analyze")["final_output"]
    assert body["status"] == "blocked"
    assert any(item["code"] == "MODULE_RULES_UNAVAILABLE" for item in body["blockers"])


def test_compliance_payload_shape(monkeypatch):
    monkeypatch.setattr(module_analysis.registry, "active_rules",
                        lambda fam, *_: [APPROVED_RULE] if fam == "compliance" else [])
    monkeypatch.setattr(module_analysis, "_resolve_sources", lambda *a, **k: EMPTY_TEMPORAL)
    out = analyze(_payload(), "compliance.analyze")
    body = out["final_output"]
    assert body["schema_version"] == "case.compliance.v2"
    assert body["status"] == "calculated"
    assert body["human_review_required"] is True
    assert body["facts_version_id"] == "fv-9"
    assert body["rules"][0]["fired"] is True
    assert body["dependency_snapshot"]["rules"][0]["contentHash"] == "h1"


def test_conviction_pulls_distinction_family(monkeypatch):
    calls = []

    def fake_active(fam, *_):
        calls.append(fam)
        return [APPROVED_RULE]

    monkeypatch.setattr(module_analysis.registry, "active_rules", fake_active)
    monkeypatch.setattr(module_analysis, "_resolve_sources", lambda *a, **k: EMPTY_TEMPORAL)
    out = analyze(_payload("conviction.analyze"), "conviction.analyze")
    assert set(calls) == {"conviction", "distinction"}
    assert out["final_output"]["schema_version"] == "case.conviction.v2"


def test_conviction_declared_single_path_is_incomplete(monkeypatch):
    one_path = {"candidate_paths": [{
        "path_id": "only", "label": "one", "charge_key": "charge.one",
        "actor_fact_key": "actor_fact", "supporting_fact_keys": ["support"],
        "contrary_fact_keys": ["contrary"],
        "when_true": {"baseline_position": "candidate"},
        "when_false": {"baseline_position": "excluded", "exclusion_reason": "reason"},
    }]}
    rule = {**APPROVED_RULE, "coverage": {"covers": ["charge.one"]}, "outcome": one_path}
    monkeypatch.setattr(module_analysis.registry, "active_rules",
                        lambda fam, *_: [rule] if fam == "conviction" else [])
    monkeypatch.setattr(module_analysis, "_resolve_sources", lambda *a, **k: EMPTY_TEMPORAL)
    body = analyze(_payload("conviction.analyze"), "conviction.analyze")["final_output"]
    assert any(item["code"] == "CONVICTION_PATHS_INCOMPLETE" for item in body["blockers"])
    assert body["candidate_paths"]
    assert body["candidate_paths"][0]["status"] == "blocked"
    assert body["candidate_paths"][0]["blockers"]


def test_temporal_semantics_ignore_candidate_declaration_labels():
    paths = [{"point": "conduct", "rules": [{"fired": True, "status": "calculated",
        "outcome": {"finding": "same", "candidate_paths": [{"label": "old"}]}}],
        "candidate_paths": [{"path_id": "p", "actor_id": "a", "charge_key": "c",
                              "baseline_position": "candidate", "verification_status": "candidate",
                              "status": "calculated", "exclusion_reason": None}]},
             {"point": "judgment", "rules": [{"fired": True, "status": "calculated",
        "outcome": {"finding": "same", "candidate_paths": [{"label": "new"}]}}],
        "candidate_paths": [{"path_id": "p", "actor_id": "a", "charge_key": "c",
                              "baseline_position": "candidate", "verification_status": "candidate",
                              "status": "calculated", "exclusion_reason": None}]}]
    assert module_analysis._path_semantic_results(paths)[0] == module_analysis._path_semantic_results(paths)[1]


def test_temporal_declared_false_rule_source_enters_dependencies(monkeypatch):
    path_rule = {**APPROVED_RULE, "sourceIds": ["temporal-source"], "coverage": {"covers": ["c"]}, "predicate": {
        "path": "facts.upstream_crime_completed.value", "op": "eq", "value": False},
        "outcome": {"candidate_paths": [{
            "path_id": "p1", "label": "p", "charge_key": "c", "actor_fact_key": "actor_fact",
            "supporting_fact_keys": ["support"], "contrary_fact_keys": ["contrary"],
            "when_true": {"baseline_position": "candidate"},
            "when_false": {"baseline_position": "excluded", "exclusion_reason": "reason"},
        }]}}
    old_rule = {**APPROVED_RULE, "sourceIds": ["asof-source"]}
    def active_rules(fam, as_of=None):
        if fam != "conviction":
            return []
        # The declared false rule exists only at the conduct point.  It must
        # enter dependencies through the temporal path, not the as-of rule.
        return [path_rule] if str(as_of) == "2024-03-01" else [old_rule]
    monkeypatch.setattr(module_analysis.registry, "active_rules", active_rules)
    monkeypatch.setattr(module_analysis, "_resolve_sources", lambda source_ids, *_: {
        "divergence": [], "blockers": [], "source_versions": [], "resolutions": {},
    })
    body = analyze(_payload("conviction.analyze"), "conviction.analyze")["final_output"]
    assert "temporal-source" in body["dependency_snapshot"]["sources"]


@pytest.mark.parametrize("known", [(datetime.date(2024, 3, 1), None),
                                    (None, datetime.date(2026, 2, 1))])
def test_single_known_legal_date_gets_its_own_temporal_path(monkeypatch, known):
    monkeypatch.setattr(module_analysis.registry, "active_rules",
                        lambda fam, *_: [APPROVED_RULE] if fam == "compliance" else [])
    paths = module_analysis._temporal_paths(
        _payload(), "compliance", "case.compliance.v2", "compliance", SNAPSHOT,
        "facts_version:fv-9", "fv-9", *known, True,
        lambda *_: {"divergence": [], "blockers": [], "source_versions": [], "resolutions": {}})
    assert len(paths) == 1
    assert paths[0]["point"] == ("conduct" if known[0] else "judgment")


def test_predicate_error_blocks_not_crashes(monkeypatch):
    bad_rule = dict(APPROVED_RULE, predicate={"all": []})
    monkeypatch.setattr(module_analysis.registry, "active_rules",
                        lambda fam, *_: [bad_rule])
    monkeypatch.setattr(module_analysis, "_resolve_sources", lambda *a, **k: EMPTY_TEMPORAL)
    out = analyze(_payload(), "compliance.analyze")
    body = out["final_output"]
    assert body["status"] == "blocked"
    assert body["blockers"][0]["code"] == "PREDICATE_INVALID"


@pytest.mark.parametrize("connections", [
    [],
    None,
    [{"verification_status": "confirmed"}],
    [{"verificationStatus": "candidate"}],
    [{"verificationStatus": "rejected"}],
    [{"verificationStatus": "unrecognized"}],
    [{"verificationStatus": "candidate"}, {"id": "malformed"}],
])
def test_conviction_requires_confirmed_jurisdiction_connection(monkeypatch, connections):
    monkeypatch.setattr(module_analysis.registry, "active_rules",
                        lambda fam, *_: [APPROVED_RULE])
    monkeypatch.setattr(module_analysis, "_resolve_sources", lambda *a, **k: EMPTY_TEMPORAL)
    payload = _payload("conviction.analyze")
    payload["metadata"]["factsSnapshot"] = {
        **SNAPSHOT,
        "entities": {"jurisdictionConnections": connections},
    }

    body = analyze(payload, "conviction.analyze")["final_output"]

    assert body["status"] == "blocked"
    assert {
        "code": "JURISDICTION_CONNECTION_UNCONFIRMED",
        "path": "entities.jurisdictionConnections",
        "message": "定罪研判需要至少一个 verificationStatus 为 confirmed 的管辖连接点",
    } in body["blockers"]


def test_conviction_accepts_any_confirmed_jurisdiction_connection(monkeypatch):
    monkeypatch.setattr(module_analysis.registry, "active_rules",
                        lambda fam, *_: [APPROVED_RULE])
    monkeypatch.setattr(module_analysis, "_resolve_sources", lambda *a, **k: EMPTY_TEMPORAL)
    payload = _payload("conviction.analyze")
    payload["metadata"]["factsSnapshot"] = {
            **SNAPSHOT,
                "entities": {"jurisdictionConnections": [
                    {"verificationStatus": "candidate"},
                    {"entityId": "jurisdiction-1", "verificationStatus": "confirmed",
                     "evidenceIds": ["proof-1"]},
            ], "evidence": [{"entityId": "proof-1", "verificationStatus": "confirmed"}]},
    }

    body = analyze(payload, "conviction.analyze")["final_output"]

    assert body["status"] == "calculated"
    assert not any(item["code"] == "JURISDICTION_CONNECTION_UNCONFIRMED"
                   for item in body["blockers"])


def test_temporal_divergence_blocks_and_keeps_two_rule_paths(monkeypatch):
    monkeypatch.setattr(module_analysis.registry, "active_rules",
                        lambda fam, *_: [APPROVED_RULE])
    monkeypatch.setattr(module_analysis, "_resolve_sources", lambda *_: {
        "divergence": [{"code": "LAW_VERSION_DIVERGENCE", "sourceKey": "law-x"}],
        "blockers": [], "source_versions": [], "resolutions": {},
    })
    monkeypatch.setattr(module_analysis.legal_temporal, "resolve_sources",
                        lambda *_: EMPTY_TEMPORAL)
    body = analyze(_payload(), "compliance.analyze")["final_output"]
    assert body["status"] == "blocked"
    assert len(body["temporal_paths"]) == 2
    assert {path["point"] for path in body["temporal_paths"]} == {"conduct", "judgment"}
    assert all(path["as_of_date"] for path in body["temporal_paths"])


def test_same_outcome_path_evidence_gap_still_blocks_top(monkeypatch):
    dated_rule = {**APPROVED_RULE, "requiredEvidenceKinds": ["judgment"]}

    def dated_active(_family, as_of):
        return [dated_rule] if str(as_of) == "2024-03-01" else [APPROVED_RULE]

    monkeypatch.setattr(module_analysis.registry, "active_rules", dated_active)
    monkeypatch.setattr(module_analysis, "_resolve_sources", lambda *_: EMPTY_TEMPORAL)
    body = analyze(_payload(), "compliance.analyze")["final_output"]
    assert body["status"] == "blocked"
    assert any(item["code"] == "TEMPORAL_PATH_BLOCKED" and item["point"] == "conduct"
               for item in body["blockers"])
    conduct = next(path for path in body["temporal_paths"] if path["point"] == "conduct")
    assert conduct["status"] == "blocked"


def test_non_fired_temporal_rules_are_not_reported_as_calculated(monkeypatch):
    unmatched = {**APPROVED_RULE, "predicate": {
        "path": "facts.upstream_crime_completed.value", "op": "eq", "value": False}}
    monkeypatch.setattr(module_analysis.registry, "active_rules", lambda *_: [unmatched])
    monkeypatch.setattr(module_analysis, "_resolve_sources", lambda *_: EMPTY_TEMPORAL)
    body = analyze(_payload(), "compliance.analyze")["final_output"]
    assert body["status"] == "not_applicable"
    assert body["rules"][0]["status"] == "not_applicable"
    assert len(body["temporal_paths"]) == 2
    assert all(path["status"] == "not_applicable" for path in body["temporal_paths"])
    assert all(path["rules"][0]["status"] == "not_applicable"
               for path in body["temporal_paths"])


def test_candidate_predicate_read_blocks_even_when_rule_does_not_fire(monkeypatch):
    monkeypatch.setattr(module_analysis.registry, "active_rules",
                        lambda fam, *_: [APPROVED_RULE] if fam == "compliance" else [])
    monkeypatch.setattr(module_analysis, "_resolve_sources", lambda *a, **k: EMPTY_TEMPORAL)
    payload = _payload()
    payload["metadata"]["factsSnapshot"] = {
        **SNAPSHOT,
        "items": [{**SNAPSHOT["items"][0], "value": False,
                    "verificationStatus": "candidate"}],
    }
    body = analyze(payload, "compliance.analyze")["final_output"]
    assert body["status"] == "blocked"
    assert any(item["code"] == "INPUT_UNCONFIRMED"
               for item in body["input_validation"]["blockers"])
    assert body["rules"][0]["input_blockers"]


def test_confirmed_jurisdiction_without_proof_is_blocked(monkeypatch):
    monkeypatch.setattr(module_analysis.registry, "active_rules",
                        lambda *_: [APPROVED_RULE])
    monkeypatch.setattr(module_analysis, "_resolve_sources", lambda *a, **k: EMPTY_TEMPORAL)
    payload = _payload("conviction.analyze")
    payload["metadata"]["factsSnapshot"] = {
        **SNAPSHOT,
        "entities": {"jurisdictionConnections": [
            {"entityId": "jurisdiction-1", "verificationStatus": "confirmed"}],
                      "evidence": [{"entityId": "proof-1", "verificationStatus": "confirmed"}]},
    }
    body = analyze(payload, "conviction.analyze")["final_output"]
    assert body["status"] == "blocked"
    assert any(item["code"] == "JURISDICTION_CONNECTION_UNCONFIRMED"
               for item in body["blockers"])


@pytest.mark.parametrize("connections", [
    [
        {"entityId": "bad-jurisdiction", "verificationStatus": "confirmed",
         "evidenceIds": []},
        {"entityId": "good-jurisdiction", "verificationStatus": "confirmed",
         "evidenceIds": ["proof-1"]},
    ],
    [
        {"entityId": "good-jurisdiction", "verificationStatus": "confirmed",
         "evidenceIds": ["proof-1"]},
        {"entityId": "bad-jurisdiction", "verificationStatus": "confirmed",
         "evidenceIds": []},
    ],
])
def test_valid_confirmed_jurisdiction_is_order_independent(monkeypatch, connections):
    monkeypatch.setattr(module_analysis.registry, "active_rules",
                        lambda *_: [APPROVED_RULE])
    monkeypatch.setattr(module_analysis, "_resolve_sources", lambda *a, **k: EMPTY_TEMPORAL)
    payload = _payload("conviction.analyze")
    payload["metadata"]["factsSnapshot"] = {
        **SNAPSHOT,
        "entities": {"jurisdictionConnections": connections,
                      "evidence": [{"entityId": "proof-1", "verificationStatus": "confirmed"}]},
    }
    body = analyze(payload, "conviction.analyze")["final_output"]
    assert body["status"] == "calculated"
    assert not any(item["code"] == "JURISDICTION_CONNECTION_UNCONFIRMED"
                   for item in body["blockers"])
