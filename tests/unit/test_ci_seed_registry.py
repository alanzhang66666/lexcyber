"""Shape and safety checks for the isolated Compose registry fixture."""

from __future__ import annotations

import pytest

from engine.adapters import document_render, module_analysis, sentencing_v2
from scripts import ci_seed_registry as fixture


def test_fixture_requires_explicit_marker(monkeypatch):
    monkeypatch.delenv("LEXCYBER_CI_FIXTURES", raising=False)
    with pytest.raises(SystemExit, match="LEXCYBER_CI_FIXTURES=1"):
        fixture._require_marker()


def test_fixture_is_explicitly_synthetic_and_covers_all_module_families():
    source = fixture._source()
    assert source["provenance"] == "LEXCYBER_CI_FIXTURES"
    assert source["coverage"] == {"fixture": True}
    rules = fixture._rules("00000000-0000-0000-0000-000000000001")
    assert {item["family"] for item in rules} == {
        "compliance", "conviction", "distinction", "sentencing"}
    assert all(str(item["rule_id"]).startswith(fixture.FIXTURE_PREFIX) for item in rules)
    template = fixture._template()
    assert template["doc_type"] == "ci.review_note"
    assert template["provenance"] == "LEXCYBER_CI_FIXTURES"
    assert "facts.ci_confirmed_marker.value" in template["body_template"]
    assert "artifacts.conviction.status" in template["body_template"]
    blocked = fixture._blocked_template()
    assert blocked["doc_type"] == "ci.blocked_note"
    assert "ci_missing_field" in blocked["body_template"]


def test_fixture_inputs_drive_all_real_adapters(monkeypatch):
    """Exercise adapter predicates and output semantics without a database."""
    source_id = "00000000-0000-0000-0000-000000000001"
    raw_rules = fixture._rules(source_id)
    rules = [{
        "ruleId": item["rule_id"], "ruleVersion": item["rule_version"],
        "predicate": item["predicate"], "outcome": item["outcome"],
        "sourceIds": item["source_ids"], "contentHash": "ci-fixture-hash",
    } for item in raw_rules]
    by_family = {}
    for item, normalized in zip(raw_rules, rules):
        by_family.setdefault(item["family"], []).append(normalized)
    monkeypatch.setattr(module_analysis.registry, "active_rules",
                        lambda family: by_family.get(family, []))
    monkeypatch.setattr(sentencing_v2.registry, "active_rules",
                        lambda family: by_family.get(family, []))
    template = fixture._template()
    monkeypatch.setattr(document_render.registry, "active_template", lambda _: {
        "templateId": template["template_id"], "templateVersion": template["template_version"],
        "fieldSchema": template["field_schema"], "bodyTemplate": template["body_template"],
        "contentHash": "ci-template-hash",
    })
    snapshot = {
        "items": [
            {"key": "ci_case_label", "value": "compose-lifecycle", "verificationStatus": "confirmed"},
            {"key": "ci_confirmed_marker", "value": "yes", "verificationStatus": "confirmed"},
            {"key": "ci_compliance_flag", "value": "true", "verificationStatus": "confirmed"},
            {"key": "ci_conviction_flag", "value": "true", "verificationStatus": "confirmed"},
            {"key": "ci_distinction_flag", "value": "true", "verificationStatus": "confirmed"},
            {"key": "ci_sentencing_flag", "value": "true", "verificationStatus": "confirmed"},
        ],
        "entities": {
            "actors": [{"id": "actor-1"}], "events": [{"id": "event-1"}],
            "evidence": [{"id": "evidence-1"}],
            "amounts": [{"kind": "crime_amount", "value": "6", "verificationStatus": "confirmed"}],
            "jurisdictionConnections": [{"id": "jurisdiction-1"}],
        },
    }
    base = {"case_id": "case-ci", "input_snapshot_ref": "facts_version:00000000-0000-0000-0000-000000000002",
            "metadata": {"factsSnapshot": snapshot}}
    compliance = module_analysis.analyze({**base, "metadata": {**base["metadata"]}}, "compliance.analyze")["final_output"]
    conviction = module_analysis.analyze({**base, "metadata": {**base["metadata"]}}, "conviction.analyze")["final_output"]
    sentencing = sentencing_v2.calculate_v2(base)["final_output"]
    assert compliance["status"] == "calculated" and any(item["fired"] for item in compliance["rules"])
    assert conviction["status"] == "calculated" and any(item["fired"] for item in conviction["rules"])
    assert sentencing["status"] == "calculated" and sentencing["results"][0]["term_months"] == 6
    rendered = document_render.render({
        **base,
        "metadata": {**base["metadata"], "docType": "ci.review_note",
                     "artifacts": {"conviction": conviction},
                     "artifactVersions": {"conviction": "00000000-0000-0000-0000-000000000003"}},
    })["final_output"]
    assert rendered["status"] == "rendered" and rendered["body"]
