"""2026-10-10 supplement predicates. Pending corpus versions are not approvals."""
from __future__ import annotations

import json
from pathlib import Path

from engine.adapters.module_analysis import _apply_assist_severity_gate, _business_status
from engine.rules.evaluator import build_view, evaluate

ROOT = Path(__file__).resolve().parents[2]
CORPUS = json.loads((ROOT / "engine/rules/corpus/core_rules.json").read_text(encoding="utf-8"))


def _rule(rule_id: str, version: str) -> dict:
    return next(row for row in CORPUS["rules"]
                if row["rule_id"] == rule_id and row["rule_version"] == version)


def _view(facts: dict, amounts: list | None = None) -> dict:
    items = [{"key": key, "value": value, "verificationStatus": "confirmed"}
             for key, value in facts.items()]
    return build_view({"items": items, "entities": {"amounts": amounts or []}})


def _fired(rule_id: str, version: str, facts: dict, amounts: list | None = None) -> bool:
    fired, _ = evaluate(_rule(rule_id, version)["predicate"], _view(facts, amounts))
    return fired


def test_signed_severity_still_ties_three_targets_to_settlement_amount():
    rule = _rule("rule-conviction-assist-severity-2019-threshold", "1.0.2")
    amounts = [{"id": "pay", "kind": "payment_settlement_amount", "value": 0,
                "verificationStatus": "confirmed"}]
    fired, _ = evaluate(rule["predicate"], _view({"assisted_targets": 3}, amounts))
    assert fired is False


def test_explicit_knowledge_and_technical_subtype_meet_elements():
    assert _fired("rule-conviction-assist-287-2-elements", "1.1.0", {
        "knowledge_of_crime": "explicit",
        "upstream_crime_established": True,
        "help_type": "server_hosting",
    }) is True


def test_presumed_knowledge_is_not_met():
    rule = _rule("rule-conviction-assist-287-2-elements", "1.1.0")
    fired, trace = evaluate(rule["predicate"], _view({
        "knowledge_of_crime": "presumed",
        "upstream_crime_established": True,
        "help_type": "payment_settlement",
    }))
    assert fired is False
    assert _business_status(fired, trace, []) == "not_met"


def test_s1_three_targets_do_not_need_settlement_amount():
    assert _fired("rule-conviction-assist-severity-2019-threshold", "1.1.0",
                  {"assisted_targets": 3}) is True
    assert _fired("rule-conviction-assist-severity-2019-threshold", "1.1.0",
                  {"assisted_targets": 2}) is False


def test_amount_paths_keep_separate_kinds():
    amounts = [
        {"id": "pay", "kind": "payment_settlement_amount", "value": 200000,
         "verificationStatus": "confirmed"},
        {"id": "funds", "kind": "provided_funds_amount", "value": 50000,
         "verificationStatus": "confirmed"},
        {"id": "gain", "kind": "illegal_gain", "value": 10000,
         "verificationStatus": "confirmed"},
    ]
    facts = {"assisted_targets": 2, "internet_admin_penalty_within_2y": False,
             "self_account_count": 0, "non_self_account_transaction": False,
             "phone_or_iot_card_count": 0}
    assert _fired("rule-conviction-assist-severity-2019-threshold", "1.1.0", facts, amounts) is True
    below = [{**row, "value": int(row["value"]) - 1} for row in amounts]
    assert _fired("rule-conviction-assist-severity-2019-threshold", "1.1.0", facts, below) is False


def test_account_flow_is_split_by_ownership_and_not_double_counted():
    parent = "11111111-1111-1111-1111-111111111111"
    child = "22222222-2222-2222-2222-222222222222"
    amounts = [
        {"id": "self-parent", "entityId": parent, "kind": "account_total_flow", "value": 300000,
         "accountOwnership": "self", "verificationStatus": "confirmed"},
        {"id": "self-child", "entityId": child, "kind": "account_total_flow", "value": 80000,
         "componentOf": parent, "accountOwnership": "self", "verificationStatus": "confirmed"},
        {"id": "unit", "entityId": "33333333-3333-3333-3333-333333333333",
         "kind": "account_total_flow", "value": 300000,
         "attributes": {"account_ownership": "unit"}, "verificationStatus": "confirmed"},
        {"id": "candidate", "entityId": "44444444-4444-4444-4444-444444444444",
         "kind": "account_total_flow", "value": 900000,
         "accountOwnership": "self", "verificationStatus": "candidate"},
    ]
    view = build_view({"items": [], "entities": {"amounts": amounts}})
    bucket = view["amounts"]["account_total_flow"]
    assert bucket["confirmedSum"] == 600000
    assert bucket["confirmedSumSelf"] == 300000
    assert bucket["confirmedSumNonSelf"] == 300000
    facts = {"assisted_targets": 2, "self_account_count": 3, "non_self_account_transaction": False,
             "phone_or_iot_card_count": 0, "internet_admin_penalty_within_2y": False}
    assert _fired("rule-conviction-assist-severity-2019-threshold", "1.1.0", facts, amounts) is True
    facts["self_account_count"] = 2
    facts["non_self_account_transaction"] = True
    assert _fired("rule-conviction-assist-severity-2019-threshold", "1.1.0", facts, amounts) is True
    facts["non_self_account_transaction"] = False
    assert _fired("rule-conviction-assist-severity-2019-threshold", "1.1.0", facts, amounts) is False


def test_concealment_hit_does_not_establish_the_offence():
    rule = _rule("rule-distinction-concealment-after-upstream", "1.1.0")
    fired, _ = evaluate(rule["predicate"], _view({
        "upstream_crime_completed": True,
        "contact_timing": "after_upstream",
        "prior_collusion": False,
        "continued_participation": False,
    }))
    assert fired is True
    assert rule["outcome"]["concealment_position"] == "candidate_only"
    assert _fired("rule-distinction-concealment-after-upstream", "1.1.0", {
        "upstream_crime_completed": True,
        "contact_timing": "after_upstream",
        "prior_collusion": True,
        "continued_participation": False,
    }) is False


def test_general_knowledge_does_not_prompt_fraud_accomplice():
    common = {"stable_cooperation": True, "cooperation_formed_before_completion": True,
              "substantial_participation": True, "support_provided": True, "prior_collusion": False}
    assert _fired("rule-distinction-fraud-accomplice-prior-collusion", "1.1.0",
                  {**common, "knowledge_specificity": "general"}) is False
    assert _fired("rule-distinction-fraud-accomplice-prior-collusion", "1.1.0",
                  {**common, "knowledge_specificity": "specific"}) is True


def test_realname_policy_without_execution_is_not_met():
    rule = _rule("rule-compliance-realname-verification", "1.1.0")
    fired, trace = evaluate(rule["predicate"], _view({
        "realname_policy_exists": True,
        "realname_verification_executed": False,
    }))
    assert fired is False
    assert _business_status(fired, trace, []) == "not_met"


def test_missing_realname_execution_stays_unknown():
    rule = _rule("rule-compliance-realname-verification", "1.1.0")
    fired, trace = evaluate(rule["predicate"], _view({"realname_policy_exists": True}))
    assert _business_status(fired, trace, []) == "unknown"


def test_recommended_charge_requires_severity():
    elements = {"ruleId": _rule("rule-conviction-assist-287-2-elements", "1.1.0")["rule_id"],
                "ruleVersion": "1.1.0", "fired": True, "status": "calculated",
                "outcome": {"charge_candidate": "assisting_information_network_crime"}}
    severity = {"ruleId": "rule-conviction-assist-severity-2019-threshold",
                "ruleVersion": "1.1.0", "fired": False, "status": "not_applicable",
                "business_status": "not_met"}
    blockers = _apply_assist_severity_gate([elements, severity])
    assert blockers[0]["code"] == "SEVERITY_GATE_UNMET"
    assert elements["outcome"]["recommended_charge"] is None
    severity["fired"] = True
    severity["status"] = "calculated"
    elements["status"] = "calculated"
    assert _apply_assist_severity_gate([elements, severity]) == []
    assert elements["outcome"]["recommended_charge"] == "assisting_information_network_crime"


def test_admin_penalty_and_card_count_do_not_auto_meet_severity():
    assert _fired("rule-conviction-assist-severity-2019-threshold", "1.1.0", {
        "assisted_targets": 2,
        "internet_admin_penalty_within_2y": True,
        "phone_or_iot_card_count": 20,
        "self_account_count": 0,
        "non_self_account_transaction": False,
    }) is False


def test_new_versions_remain_pending_and_do_not_replace_signed_versions():
    pending = [row for row in CORPUS["rules"] if row["rule_version"] == "1.1.0"]
    assert {row["rule_id"] for row in pending} == {
        "rule-conviction-assist-287-2-elements",
        "rule-conviction-assist-severity-2019-threshold",
        "rule-distinction-concealment-after-upstream",
        "rule-distinction-fraud-accomplice-prior-collusion",
        "rule-compliance-logs-retention-6m",
        "rule-compliance-realname-verification",
    }
    assert all(row["legal_review_status"] == "pending" for row in pending)
    assert _rule("rule-sentencing-assist-base", "1.0.2")["outcome"]["calculation"]["base_tiers"][2]["months"] == 9
