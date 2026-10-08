"""Actual corpus inputs need their own proofs, independent of required kinds."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from uuid import uuid4

import pytest

from engine.adapters import sentencing_v2


def _corpus_rule():
    corpus = json.loads((Path(__file__).resolve().parents[2] / "engine/rules/corpus/core_rules.json").read_text())
    raw = next(row for row in corpus["rules"] if row["rule_id"] == "rule-sentencing-assist-base")
    return {"ruleId": raw["rule_id"], "ruleVersion": raw["rule_version"],
            "predicate": raw["predicate"], "outcome": raw["outcome"],
            "requiredEvidenceKinds": raw["required_evidence_kinds"],
            "sourceIds": [], "contentHash": "offline-corpus-fixture"}


def _payload():
    rule = _corpus_rule()
    proof_id = str(uuid4())
    evidence = [{"entityId": proof_id, "id": "parameter-proof", "type": "document",
                 "verificationStatus": "confirmed"},
                *[{"entityId": str(uuid4()), "type": kind, "verificationStatus": "confirmed"}
                  for kind in rule["requiredEvidenceKinds"]]]
    facts = [{"entityId": str(uuid4()), "key": key, "value": value,
              "verificationStatus": "confirmed", "evidenceIds": [proof_id]}
             for key, value in (("upstream_crime_established", True), ("has_surrender", True),
                                ("has_confession", False), ("has_guilty_plea", False))]
    snapshot = {"items": facts, "entities": {
        "evidence": evidence, "amounts": [{"entityId": str(uuid4()), "kind": "payment_settlement_amount",
                                           "value": 200000, "verificationStatus": "confirmed",
                                           "evidenceIds": [proof_id]}],
    }}
    return {"case_id": str(uuid4()), "input_snapshot_ref": "facts_version:" + str(uuid4()),
            "metadata": {"asOfDate": "2025-01-01", "factsSnapshot": snapshot,
                         "artifactVersions": {"conviction": str(uuid4())}}}


def _fact(payload, key):
    return next(row for row in payload["metadata"]["factsSnapshot"]["items"] if row["key"] == key)


def _run(monkeypatch, payload, rules=None):
    # Only registry I/O is replaced. Predicates, ratios, tiers, validators and
    # adapters are actual repository code; this is not formal legal approval.
    monkeypatch.setattr(sentencing_v2.registry, "active_rules", rules or (lambda *_: [_corpus_rule()]))
    before = copy.deepcopy(payload)
    result = sentencing_v2.calculate_v2(payload)["final_output"]
    assert payload == before
    return result


def _assert_blocked_without_numbers(body):
    assert body["status"] == "blocked"
    assert body["input_validation"]["status"] == "blocked"
    for result in [*body["results"], *[row for path in body["temporal_paths"] for row in path["results"]]]:
        assert result["term_months"] is None and result["fine"] is None
        assert result["steps"] == []


@pytest.mark.parametrize("surrender,months", [(True, 8.4), (False, 12.0)])
def test_actual_corpus_confirmed_linked_parameters_keep_original_ratios(monkeypatch, surrender, months):
    payload = _payload()
    _fact(payload, "has_surrender")["value"] = surrender
    body = _run(monkeypatch, payload)
    assert body["status"] == "calculated" and body["results"][0]["term_months"] == months
    marker = body["input_validation"]
    assert marker["status"] == "verified" and marker["blockers"] == []
    assert any(check["path"] == "facts.has_surrender.value"
               and check["inputIds"] and check["evidenceIds"] for check in marker["checks"])
    assert {check["phase"].split(":")[0] for check in marker["checks"]} >= {"rule_predicate", "base_tier", "adjustment"}


@pytest.mark.parametrize("surrender", [True, False])
def test_actual_corpus_candidate_adjustment_blocks_even_when_false(monkeypatch, surrender):
    payload = _payload()
    _fact(payload, "has_surrender").update(value=surrender, verificationStatus="candidate")
    body = _run(monkeypatch, payload)
    _assert_blocked_without_numbers(body)
    assert any(check["path"] == "facts.has_surrender.value" and check["status"] == "blocked"
               for check in body["input_validation"]["checks"])
    assert all(body["results"][0]["evidence_checks"]["matchedEvidenceIds"].values())


@pytest.mark.parametrize("bad_proof", ["unlinked", "candidate"])
def test_required_kinds_do_not_supply_parameter_proof(monkeypatch, bad_proof):
    payload = _payload()
    if bad_proof == "unlinked":
        _fact(payload, "has_surrender")["evidenceIds"] = []
    else:
        # Keep all other actual inputs valid to reach the adjustment read.
        candidate_id = str(uuid4())
        payload["metadata"]["factsSnapshot"]["entities"]["evidence"].append({
            "entityId": candidate_id, "type": "document", "verificationStatus": "candidate"})
        _fact(payload, "has_surrender")["evidenceIds"] = [candidate_id]
    body = _run(monkeypatch, payload)
    _assert_blocked_without_numbers(body)
    assert any(check["path"] == "facts.has_surrender.value" and check["status"] == "blocked"
               for check in body["input_validation"]["checks"])


@pytest.mark.parametrize("damage", ["no_proof", "duplicate"])
def test_legal_dates_need_unique_verified_proof_and_mask_all_paths(monkeypatch, damage):
    payload = _payload()
    snapshot = payload["metadata"]["factsSnapshot"]
    proof_id = snapshot["entities"]["evidence"][0]["entityId"]
    dates = [{"entityId": str(uuid4()), "key": key, "value": value,
              "verificationStatus": "confirmed", "evidenceIds": [proof_id]}
             for key, value in (("conduct_date", "2024-06-01"), ("judgment_date", "2026-01-01"))]
    if damage == "no_proof":
        dates[0]["evidenceIds"] = []
    else:
        dates.append({**dates[0], "entityId": str(uuid4())})
    snapshot["items"].extend(dates)
    body = _run(monkeypatch, payload)
    _assert_blocked_without_numbers(body)
    assert len(body["temporal_paths"]) == 2
    assert any(check["phase"] == "legal_dates" and check["status"] == "blocked"
               for check in body["input_validation"]["checks"])


def test_input_read_only_at_conduct_point_blocks_primary_and_judgment_numbers(monkeypatch):
    payload = _payload()
    snapshot = payload["metadata"]["factsSnapshot"]
    proof_id = snapshot["entities"]["evidence"][0]["entityId"]
    snapshot["items"].extend([
        {"entityId": str(uuid4()), "key": key, "value": value, "verificationStatus": "confirmed",
         "evidenceIds": [proof_id]} for key, value in (
             ("conduct_date", "2024-06-01"), ("judgment_date", "2026-01-01"))])
    snapshot["items"].append({"entityId": str(uuid4()), "key": "conduct_selector", "value": False,
                              "verificationStatus": "candidate", "evidenceIds": [proof_id]})

    def dated_rules(_family, point):
        rule = _corpus_rule()
        if str(point) == "2024-06-01":
            rule["predicate"] = {"path": "facts.conduct_selector.value", "op": "eq", "value": True}
        return [rule]

    body = _run(monkeypatch, payload, dated_rules)
    _assert_blocked_without_numbers(body)
    checks = body["input_validation"]["checks"]
    assert any(check["point"] == "conduct" and check["path"] == "facts.conduct_selector.value"
               and check["status"] == "blocked" for check in checks)
    judgment = next(path for path in body["temporal_paths"] if path["point"] == "judgment")
    assert not any(check["path"] == "facts.conduct_selector.value"
                   for check in judgment["input_validation"]["checks"])
