from engine.rules.conviction_paths import (
    execute_candidate_paths,
    validate_candidate_path_definitions,
)
from engine.rules.evaluator import build_view
from engine.rules.inputs import InputValidator


def _definition(**overrides):
    item = {
        "path_id": "p1", "label": "helping", "charge_key": "charge.helping",
        "actor_fact_key": "actor_fact", "supporting_fact_keys": ["support"],
        "contrary_fact_keys": ["contrary"], "when_true": {"baseline_position": "candidate"},
        "when_false": {"baseline_position": "excluded", "exclusion_reason": "not proved"},
    }
    item.update(overrides)
    return item


def _snapshot():
    return {
        "items": [
            {"key": "actor_fact", "entityId": "fact-actor", "actorId": "actor-1", "value": True,
             "verificationStatus": "confirmed", "evidenceIds": ["proof-1"]},
            {"key": "support", "entityId": "fact-support", "actorId": "actor-1", "value": True,
             "verificationStatus": "confirmed", "evidenceIds": ["proof-1"]},
            {"key": "contrary", "entityId": "fact-contrary", "actorId": "actor-1", "value": False,
             "verificationStatus": "confirmed", "evidenceIds": ["proof-1"]},
        ],
        "entities": {"actors": [{"entityId": "actor-1", "name": "A"}],
                     "evidence": [{"entityId": "proof-1", "verificationStatus": "confirmed"}]},
    }


def _rule(outcome):
    return {"ruleId": "r1", "ruleVersion": "1", "sourceIds": ["source-1"], "outcome": outcome}


def test_definitions_require_both_branches_and_reject_duplicates():
    outcome = {"candidate_paths": [_definition(), _definition()]}
    blockers = validate_candidate_path_definitions(outcome)
    assert any(item["code"] == "CONVICTION_PATH_DUPLICATE" for item in blockers)
    assert validate_candidate_path_definitions({"conclusion": "legacy"}) == []


def test_execution_selects_declared_false_exclusion_and_raw_ids():
    snapshot = _snapshot()
    validator = InputValidator(snapshot, build_view(snapshot))
    rows, blockers = execute_candidate_paths(_rule({"candidate_paths": [_definition()]}), snapshot,
                                             validator, fired=False)
    assert not blockers
    assert rows[0]["baseline_position"] == "excluded"
    assert rows[0]["exclusion_reason"] == "not proved"
    assert rows[0]["actor_id"] == "actor-1"
    assert rows[0]["supporting_evidence_ids"] == ["proof-1"]


def test_subjective_contrary_proof_blocks_conflicted_path():
    definition = _definition(
        contrary_fact_keys=["contrary"], subjective=True,
        when_true={"baseline_position": "candidate"},
    )
    snapshot = _snapshot()
    validator = InputValidator(snapshot, build_view(snapshot))
    rows, blockers = execute_candidate_paths(_rule({"candidate_paths": [definition]}), snapshot,
                                             validator, fired=True)
    assert rows[0]["status"] == "blocked"
    assert rows[0]["verification_status"] == "conflicted"
    assert rows[0]["baseline_position"] is None
    assert any(item["code"] == "CONVICTION_PATH_CONFLICT" for item in blockers)


def test_cross_actor_fact_is_blocked():
    definition = _definition()
    snapshot = _snapshot()
    snapshot["items"][1]["actorId"] = "actor-2"
    snapshot["entities"]["actors"].append({"entityId": "actor-2"})
    validator = InputValidator(snapshot, build_view(snapshot))
    rows, blockers = execute_candidate_paths(_rule({"candidate_paths": [definition]}), snapshot,
                                             validator, fired=True)
    assert rows[0]["status"] == "blocked"
    assert any(item["code"] == "CONVICTION_PATH_ACTOR_MISMATCH" for item in blockers)


def test_proof_ids_are_canonical_and_snapshot_is_not_mutated():
    snapshot = _snapshot()
    snapshot["entities"]["evidence"][0]["id"] = "legacy-proof"
    before = repr(snapshot)
    validator = InputValidator(snapshot, build_view(snapshot))
    rows, blockers = execute_candidate_paths(_rule({"candidate_paths": [_definition()]}), snapshot,
                                             validator, fired=True)
    assert not blockers
    assert rows[0]["supporting_evidence_ids"] == ["proof-1"]
    assert repr(snapshot) == before


def test_malformed_json_and_unconfirmed_proof_fail_closed():
    malformed = {"candidate_paths": None}
    assert validate_candidate_path_definitions(malformed)
    snapshot = _snapshot()
    snapshot["entities"]["evidence"][0]["verificationStatus"] = "candidate"
    validator = InputValidator(snapshot, build_view(snapshot))
    rows, blockers = execute_candidate_paths(_rule({"candidate_paths": [_definition()]}), snapshot,
                                             validator, fired=True)
    assert rows[0]["status"] == "blocked"
    assert any(item["code"] == "INPUT_UNCONFIRMED" for item in blockers)


def test_uuid_actor_aliases_and_missing_source_are_checked():
    snapshot = _snapshot()
    snapshot["entities"]["actors"][0] = {"entityId": "550e8400-e29b-41d4-a716-446655440000"}
    snapshot["items"][0]["actorId"] = "550E8400-E29B-41D4-A716-446655440000"
    snapshot["items"][1]["actorId"] = snapshot["items"][0]["actorId"]
    validator = InputValidator(snapshot, build_view(snapshot))
    rows, blockers = execute_candidate_paths({**_rule({"candidate_paths": [_definition()]}), "sourceIds": []}, snapshot,
                                             validator, fired=True)
    assert rows[0]["status"] == "blocked"
    assert any(item["code"] == "CONVICTION_PATH_LEGAL_SOURCE_MISSING" for item in blockers)


def test_shared_actor_alias_on_two_rows_blocks_role_fact():
    snapshot = _snapshot()
    snapshot["entities"]["actors"].append({"entityId": "actor-2", "id": "actor-1"})
    validator = InputValidator(snapshot, build_view(snapshot))
    rows, blockers = execute_candidate_paths(_rule({"candidate_paths": [_definition()]}), snapshot,
                                             validator, fired=True)
    assert rows[0]["status"] == "blocked"
    assert any(item["code"] == "CONVICTION_PATH_ACTOR_AMBIGUOUS" for item in blockers)
