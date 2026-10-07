"""Seed an isolated, synthetic rule registry for the Compose lifecycle smoke.

This file is intentionally CI-only.  It refuses to run unless the Compose job
sets ``LEXCYBER_CI_FIXTURES=1``.  The records are clearly labelled fixtures;
they are registered and signed off through the normal registry functions so
the smoke exercises the same gate as production, without changing the legal
corpus or pretending to provide legal approval.
"""

from __future__ import annotations

import os
from datetime import date

from engine.rules import registry

FIXTURE_PREFIX = "ci-fixture-"
REVIEWER = "ci-fixture-reviewer"
ROLE = "automated-ci-fixture"


def _require_marker() -> None:
    if os.environ.get("LEXCYBER_CI_FIXTURES") != "1":
        raise SystemExit("refusing CI registry seed without LEXCYBER_CI_FIXTURES=1")


def _source() -> dict[str, object]:
    return {
        "source_key": FIXTURE_PREFIX + "source",
        "title": "LexCyber CI synthetic source (not legal authority)",
        "document_number": "CI-FIXTURE-ONLY",
        "article": "fixture",
        "jurisdiction": "CI",
        "authority": "policy",
        "source_version": "1.0.0",
        "effective_from": date(2026, 1, 1).isoformat(),
        "excerpt": "Synthetic test input. Not a legal source and not for production use.",
        "provenance": "LEXCYBER_CI_FIXTURES",
        "coverage": {"fixture": True},
    }


def _temporal_source(version: str, effective_from: str, effective_to: str | None = None) -> dict[str, object]:
    return {
        "source_key": FIXTURE_PREFIX + "temporal-source",
        "title": "LexCyber CI temporal synthetic source (not legal authority)",
        "document_number": "CI-TEMPORAL-FIXTURE-ONLY",
        "article": "fixture-temporal",
        "jurisdiction": "CI",
        "authority": "policy",
        "source_version": version,
        "effective_from": effective_from,
        "effective_to": effective_to,
        "excerpt": "Synthetic temporal test input. Not a legal source and not for production use.",
        "provenance": "LEXCYBER_CI_FIXTURES",
        "coverage": {"fixture": True, "temporal": True},
    }


def _rules(source_id: str, temporal_source_ids: tuple[str, str] | None = None) -> list[dict[str, object]]:
    def rule(rule_id: str, family: str, field: str, outcome: dict[str, object],
             *, rule_version: str = "1.0.0", source_ids: list[str] | None = None,
             effective_from: str | None = None, effective_to: str | None = None,
             required_evidence_kinds: list[str] | None = None) -> dict[str, object]:
        return {
            "rule_id": FIXTURE_PREFIX + rule_id,
            "rule_version": rule_version,
            "family": family,
            # These isolated flags are optional fixture selectors.  Guard their
            # absence explicitly so an unread value never masquerades as false.
            "predicate": {"all": [
                {"path": f"facts.{field}", "op": "exists"},
                {"path": f"facts.{field}.value", "op": "eq", "value": True},
            ]},
            "outcome": outcome,
            "source_ids": source_ids or [source_id],
            "coverage": {"fixture": True, "name": FIXTURE_PREFIX + rule_id},
            "required_evidence_kinds": required_evidence_kinds or [],
            "effective_from": effective_from,
            "effective_to": effective_to,
        }

    component_guard = rule("component-amount-threshold", "conviction", "ci_component_guard_flag",
                           {"finding": "ci_fixture_amount_threshold"})
    component_guard["predicate"] = {"all": [
        component_guard["predicate"],
        {"path": "amounts.payment_settlement_amount.confirmedSum", "op": "gte", "value": 200000},
    ]}
    evidence_guard = rule("evidence-guard", "compliance", "ci_evidence_guard_flag",
                          {"finding": "ci_fixture_evidence_guard"},
                          required_evidence_kinds=["service_log"])
    rules = [
        rule("compliance", "compliance", "ci_compliance_flag", {"finding": "ci_fixture_compliance"}),
        rule("conviction", "conviction", "ci_conviction_flag", {"finding": "ci_fixture_conviction"}),
        rule("distinction", "distinction", "ci_distinction_flag", {"finding": "ci_fixture_distinction"}),
        rule("sentencing", "sentencing", "ci_sentencing_flag", {
            "calculation": {"base_months": 6, "fine": {"mode": "ci_fixture"}},
        }),
        component_guard,
        evidence_guard,
    ]
    if temporal_source_ids is not None:
        rules.extend([
            rule("temporal-guard", "compliance", "ci_temporal_guard_flag",
                 {"finding": "ci_fixture_temporal_old"}, rule_version="2020.1",
                 source_ids=[temporal_source_ids[0]], effective_from="2020-01-01",
                 effective_to="2024-12-31"),
            rule("temporal-guard", "compliance", "ci_temporal_guard_flag",
                 {"finding": "ci_fixture_temporal_new"}, rule_version="2025.1",
                 source_ids=[temporal_source_ids[1]], effective_from="2025-01-01"),
        ])
    return rules


def _template() -> dict[str, object]:
    return {
        "template_id": FIXTURE_PREFIX + "review-note",
        "template_version": "1.0.0",
        "doc_type": "ci.review_note",
        "field_schema": {"required": ["facts.ci_case_label.value"]},
        "body_template": (
            "CI FIXTURE REVIEW NOTE (not a legal document)\n"
            "case={{case_id}} label={{facts.ci_case_label.value}}\n"
            "confirmed facts={{facts.ci_confirmed_marker.value}}\n"
            "conviction status={{artifacts.conviction.status}}\n"
        ),
        "provenance": "LEXCYBER_CI_FIXTURES",
    }


def _blocked_template() -> dict[str, object]:
    return {
        "template_id": FIXTURE_PREFIX + "blocked-note",
        "template_version": "1.0.0",
        "doc_type": "ci.blocked_note",
        "field_schema": {"required": ["facts.ci_missing_field.value"]},
        "body_template": "CI blocked fixture {{facts.ci_missing_field.value}}",
        "provenance": "LEXCYBER_CI_FIXTURES",
    }


def seed() -> dict[str, object]:
    _require_marker()
    before = registry.capabilities()
    expected = ("compliance", "conviction", "sentencing")
    already_available = [name for name in expected if before["modules"][name]["available"]]
    if already_available:
        raise RuntimeError(
            "refusing to seed over approved rules in CI database; initial registry must be fail-closed: "
            + ", ".join(already_available))
    source_item = _source()
    source_id = str(registry.register_legal_source(source_item)["sourceId"])
    registry.signoff("legal_source", f"{source_item['source_key']}@{source_item['source_version']}",
                     REVIEWER, ROLE, "approved",
                     "CI synthetic fixture only; not a legal review or production approval")

    temporal_sources = [_temporal_source("2020.1", "2020-01-01", "2024-12-31"),
                        _temporal_source("2025.1", "2025-01-01")]
    temporal_source_ids = tuple(
        str(registry.register_legal_source(item)["sourceId"]) for item in temporal_sources)
    for item in temporal_sources:
        registry.signoff("legal_source", f"{item['source_key']}@{item['source_version']}",
                         REVIEWER, ROLE, "approved",
                         "CI synthetic fixture only; not a legal review or production approval")
    registry.link_supersession(temporal_source_ids[0], temporal_source_ids[1],
                               note="CI synthetic temporal fixture explicit supersession")

    rules = []
    for item in _rules(source_id, temporal_source_ids):
        registry.register_rule_package(item)
        key = f"{item['rule_id']}@{item['rule_version']}"
        registry.signoff("rule", key, REVIEWER, ROLE, "approved",
                         "CI synthetic fixture only; not a legal review or production approval")
        rules.append(key)

    template = _template()
    registry.register_template(template)
    registry.signoff("template", f"{template['template_id']}@{template['template_version']}",
                     REVIEWER, ROLE, "approved",
                     "CI synthetic fixture only; not a legal review or production approval")
    blocked = _blocked_template()
    registry.register_template(blocked)
    registry.signoff("template", f"{blocked['template_id']}@{blocked['template_version']}",
                     REVIEWER, ROLE, "approved",
                     "CI synthetic fixture only; not a legal review or production approval")

    caps = registry.capabilities()
    unavailable = [name for name in expected if not caps["modules"][name]["available"]]
    if unavailable:
        raise RuntimeError(f"CI fixture seed did not enable modules: {unavailable}")
    if "ci.review_note" not in caps["modules"]["draft"]["approvedDocTypes"]:
        raise RuntimeError("CI fixture template was not approved")
    if "ci.blocked_note" not in caps["modules"]["draft"]["approvedDocTypes"]:
        raise RuntimeError("CI blocked fixture template was not approved")
    return {"source": source_item["source_key"], "temporalSources": [item["source_key"] for item in temporal_sources],
            "rules": rules,
            "template": template["doc_type"], "capabilities": caps}


if __name__ == "__main__":
    _require_marker()
    print(seed(), flush=True)
