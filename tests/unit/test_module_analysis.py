"""模块分析适配器单测：registry 打桩，验证 payload 形状与阻断语义。"""
from __future__ import annotations

import pytest

from engine.adapters import module_analysis
from engine.adapters.module_analysis import ModuleAnalysisError, analyze

SNAPSHOT = {
    "items": [
        {"key": "upstream_crime_completed", "value": True, "verificationStatus": "confirmed"},
        {"key": "conduct_date", "value": "2024-03-01", "verificationStatus": "confirmed"},
        {"key": "judgment_date", "value": "2026-02-01", "verificationStatus": "confirmed"},
    ],
    "entities": {},
}

APPROVED_RULE = {
    "rulePackageId": "rp-1", "ruleId": "rule-test", "ruleVersion": "1.0.0",
    "sourceIds": ["s1"], "predicate": {"path": "facts.upstream_crime_completed.value",
                                       "op": "eq", "value": True},
    "outcome": {"conclusion": "upstream_done"},
    "requiredEvidenceKinds": [], "coverage": {}, "contentHash": "h1",
}


def _payload(task_type="compliance.analyze"):
    return {"case_id": "case-1", "input_snapshot_ref": "facts_version:fv-9",
            "metadata": {"taskType": task_type, "factsSnapshot": SNAPSHOT}}


def test_missing_snapshot_fails_closed(monkeypatch):
    monkeypatch.setattr(module_analysis.registry, "active_rules",
                        lambda fam: [APPROVED_RULE])
    payload = _payload()
    payload["metadata"] = {"taskType": "compliance.analyze"}
    with pytest.raises(ModuleAnalysisError) as err:
        analyze(payload, "compliance.analyze")
    assert err.value.code == "FACTS_SNAPSHOT_MISSING"


def test_no_approved_rules_fails_closed(monkeypatch):
    monkeypatch.setattr(module_analysis.registry, "active_rules", lambda fam: [])
    with pytest.raises(ModuleAnalysisError) as err:
        analyze(_payload(), "compliance.analyze")
    assert err.value.code == "MODULE_RULES_UNAVAILABLE"


def test_compliance_payload_shape(monkeypatch):
    monkeypatch.setattr(module_analysis.registry, "active_rules",
                        lambda fam: [APPROVED_RULE] if fam == "compliance" else [])
    monkeypatch.setattr(module_analysis, "_resolve_sources", lambda *a, **k: [])
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

    def fake_active(fam):
        calls.append(fam)
        return [APPROVED_RULE]

    monkeypatch.setattr(module_analysis.registry, "active_rules", fake_active)
    monkeypatch.setattr(module_analysis, "_resolve_sources", lambda *a, **k: [])
    out = analyze(_payload("conviction.analyze"), "conviction.analyze")
    assert set(calls) == {"conviction", "distinction"}
    assert out["final_output"]["schema_version"] == "case.conviction.v2"


def test_predicate_error_blocks_not_crashes(monkeypatch):
    bad_rule = dict(APPROVED_RULE, predicate={"all": []})
    monkeypatch.setattr(module_analysis.registry, "active_rules",
                        lambda fam: [bad_rule])
    monkeypatch.setattr(module_analysis, "_resolve_sources", lambda *a, **k: [])
    out = analyze(_payload(), "compliance.analyze")
    body = out["final_output"]
    assert body["status"] == "blocked"
    assert body["blockers"][0]["code"] == "PREDICATE_INVALID"
