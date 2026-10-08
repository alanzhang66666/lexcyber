from __future__ import annotations

from engine.rules.evaluator import build_view, evaluate
from engine.rules.inputs import InputValidator

EVIDENCE_ID = "11111111-1111-1111-1111-111111111111"
ACTOR_ID = "22222222-2222-2222-2222-222222222222"


def evidence(*, status: str = "confirmed", external: str = "bank-flow") -> dict:
    return {"entityId": EVIDENCE_ID, "id": external, "externalId": external,
            "type": "transaction_flow", "verificationStatus": status}


def snapshot(*, fact_status: str = "confirmed", evidence_rows=None,
             fact_evidence=None, amounts=None, actors=None, events=None) -> dict:
    return {
        "items": [{"entityId": "33333333-3333-3333-3333-333333333333",
                   "id": "f-amount", "key": "amount", "value": "200",
                   "verificationStatus": fact_status,
                   "evidenceIds": ["bank-flow"] if fact_evidence is None else fact_evidence}],
        "entities": {
            "evidence": [evidence()] if evidence_rows is None else evidence_rows,
            "amounts": ([{"entityId": "44444444-4444-4444-4444-444444444444",
                           "id": "amount-1", "kind": "crime_amount", "value": "200",
                           "verificationStatus": "confirmed", "evidenceIds": ["bank-flow"]}]
                         if amounts is None else amounts),
            "actors": [] if actors is None else actors,
            "events": [] if events is None else events,
            "jurisdictionConnections": [],
        },
    }


def validator(snap: dict) -> InputValidator:
    return InputValidator(snap, build_view(snap))


def test_confirmed_fact_and_amount_have_complete_proof():
    snap = snapshot()
    v = validator(snap)
    assert v.check_path("facts.amount.value") == []
    assert v.check_path("amounts.crime_amount.sum") == []
    assert v.summary()["status"] == "verified"


def test_candidate_fact_blocks_even_when_predicate_is_false():
    snap = snapshot(fact_status="candidate")
    fired, trace = evaluate({"path": "facts.amount.value", "op": "eq", "value": "999"}, build_view(snap))
    assert fired is False
    blockers = validator(snap).check_trace(trace)
    assert any(item["code"] == "INPUT_UNCONFIRMED" for item in blockers)


def test_missing_and_unconfirmed_evidence_block():
    missing = snapshot(fact_evidence=["missing-evidence"])
    assert any(item["code"] == "INPUT_EVIDENCE_INVALID"
               for item in validator(missing).check_path("facts.amount.value"))
    unconfirmed = snapshot(evidence_rows=[evidence(status="candidate")])
    assert any(item["code"] == "INPUT_UNCONFIRMED"
               for item in validator(unconfirmed).check_path("facts.amount.value"))


def test_duplicate_evidence_aliases_are_ambiguous():
    second = {**evidence(), "entityId": "55555555-5555-5555-5555-555555555555"}
    snap = snapshot(evidence_rows=[evidence(), second])
    blockers = validator(snap).check_path("facts.amount.value")
    assert any(item["code"] == "INPUT_EVIDENCE_AMBIGUOUS" for item in blockers)


def test_duplicate_fact_keys_block_only_when_read():
    snap = snapshot()
    snap["items"].append({**snap["items"][0], "entityId": "66666666-6666-6666-6666-666666666666", "value": "200"})
    v = validator(snap)
    assert v.check_path("facts.unused.value")  # ordinary missing path
    assert any(item["code"] == "INPUT_AMBIGUOUS" for item in v.check_path("facts.amount.value"))


def test_lazy_short_circuit_does_not_validate_unused_path():
    snap = snapshot(fact_status="candidate")
    predicate = {"all": [{"path": "facts.missing.value", "op": "exists"},
                          {"path": "facts.amount.value", "op": "eq", "value": "200"}]}
    fired, trace = evaluate(predicate, build_view(snap))
    assert fired is False
    assert [entry["path"] for entry in trace] == ["facts.missing.value"]
    assert validator(snap).check_trace(trace) == []


def test_count_and_confirmed_count_validate_their_actual_rows():
    snap = snapshot()
    snap["entities"]["amounts"].append({"entityId": "77777777-7777-7777-7777-777777777777",
                                           "id": "amount-2", "kind": "crime_amount", "value": "1",
                                           "verificationStatus": "candidate", "evidenceIds": ["bank-flow"]})
    v = validator(snap)
    assert v.check_path("amounts.crime_amount.count")
    assert v.check_path("amounts.crime_amount.confirmedCount") == []


def test_invalid_numeric_and_empty_aggregate_block_but_confirmed_zero_passes():
    bad = snapshot(amounts=[{"entityId": "88888888-8888-8888-8888-888888888888", "id": "bad",
                             "kind": "crime_amount", "value": "not-a-number",
                             "verificationStatus": "confirmed", "evidenceIds": ["bank-flow"]}])
    assert any(item["code"] == "INPUT_INVALID_NUMERIC"
               for item in validator(bad).check_path("amounts.crime_amount.sum"))
    empty = snapshot(amounts=[])
    assert any(item["code"] == "INPUT_EMPTY"
               for item in validator(empty).check_path("amounts.crime_amount.sum"))
    zero = snapshot(amounts=[{"entityId": "99999999-9999-9999-9999-999999999999", "id": "zero",
                              "kind": "crime_amount", "value": "0",
                              "verificationStatus": "confirmed", "evidenceIds": ["bank-flow"]}])
    assert validator(zero).check_path("amounts.crime_amount.sum") == []


def test_candidate_child_covered_by_confirmed_parent_is_not_a_confirmed_sum_input():
    parent = {"entityId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "id": "parent",
              "kind": "crime_amount", "value": "200", "verificationStatus": "confirmed",
              "evidenceIds": ["bank-flow"]}
    child = {"entityId": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", "id": "child",
             "kind": "crime_amount", "value": "50", "componentOf": "parent",
             "verificationStatus": "candidate", "evidenceIds": ["bank-flow"]}
    snap = snapshot(amounts=[parent, child])
    assert validator(snap).check_path("amounts.crime_amount.confirmedSum") == []


def test_uuid_aliases_are_normalized_and_unknown_paths_fail_closed():
    upper = {**evidence(), "id": EVIDENCE_ID.upper(), "externalId": EVIDENCE_ID.upper()}
    snap = snapshot(evidence_rows=[upper], fact_evidence=[EVIDENCE_ID.upper()])
    assert validator(snap).check_path("facts.amount.value") == []
    blockers = validator(snap).check_path("facts.amount.unknown")
    assert any(item["code"] == "INPUT_PATH_UNKNOWN" for item in blockers)


def test_exists_missing_probe_can_be_structural_but_present_still_requires_proof():
    snap = snapshot(fact_status="candidate")
    v = validator(snap)
    assert v.check_path("facts.optional.value", structural=True) == []
    assert v.check_path("facts.amount.value", structural=True)


def test_actor_and_event_reads_fail_without_native_evidence_proof():
    actor = {"entityId": ACTOR_ID, "id": "actor-1", "name": "张某", "verificationStatus": "confirmed"}
    snap = snapshot(actors=[actor])
    blockers = validator(snap).check_path("entities.actors.count")
    assert any(item["code"] == "INPUT_ACTOR_EVIDENCE_MISSING" for item in blockers)


def test_administrative_paths_are_document_only():
    assert validator(snapshot()).check_path("case_id", phase="predicate")
    assert validator(snapshot()).check_path("case_id", phase="document") == []


def test_structural_probe_cannot_hide_later_ordinary_missing_read():
    snap = snapshot()
    snap["items"][0]["attributes"] = {}
    v = validator(snap)
    assert v.check_path("facts.amount.attributes.absent", structural=True) == []
    blockers = v.check_path("facts.amount.attributes.absent")
    assert any(item["code"] == "INPUT_MISSING" for item in blockers)
    assert v.summary()["status"] == "blocked"


def test_repeated_blocked_path_returns_blockers_for_each_branch():
    v = validator(snapshot(fact_status="candidate"))
    first = v.check_path("facts.amount.value")
    second = v.check_path("facts.amount.value")
    assert first and second
    assert second[0]["code"] == "INPUT_UNCONFIRMED"


def test_duplicate_canonical_evidence_rejects_every_alias():
    second = {**evidence(), "id": "other-alias", "externalId": "other-alias"}
    snap = snapshot(evidence_rows=[evidence(), second])
    first_alias = validator(snap).check_path("facts.amount.value")
    assert any(item["code"] == "INPUT_EVIDENCE_AMBIGUOUS" for item in first_alias)
    snap["items"][0]["evidenceIds"] = ["other-alias"]
    later_alias = validator(snap).check_path("facts.amount.value")
    assert any(item["code"] == "INPUT_EVIDENCE_AMBIGUOUS" for item in later_alias)


def test_null_and_missing_nested_fact_fields_block_actual_reads():
    snap = snapshot()
    snap["items"][0]["attributes"] = {}
    v = validator(snap)
    assert any(item["code"] == "INPUT_MISSING"
               for item in v.check_path("facts.amount.attributes.absent"))
    snap["items"][0]["value"] = None
    assert any(item["code"] == "INPUT_MISSING"
               for item in validator(snap).check_path("facts.amount.value"))


def test_malformed_amount_array_cannot_be_dropped_by_build_view():
    snap = snapshot()
    snap["entities"]["amounts"].append(42)
    view = build_view(snap)
    assert any(item["code"] == "INPUT_SCHEMA_INVALID"
               for item in InputValidator(snap, view).check_path("amounts.crime_amount.sum"))


def test_entity_and_amount_item_paths_validate_selected_rows_and_nested_fields():
    snap = snapshot()
    amount = snap["entities"]["amounts"][0]
    assert validator(snap).check_path("amounts.crime_amount.items.0.value") == []
    assert validator(snap).check_path("entities.evidence.items.0.type") == []
    assert validator(snap).check_path("entities.evidence.items.-1.type")
    amount.pop("value")
    assert any(item["code"] == "INPUT_MISSING"
               for item in validator(snap).check_path("amounts.crime_amount.items.0.value"))


def test_external_alias_cannot_supply_fact_canonical_identity():
    snap = snapshot()
    fact = snap["items"][0]
    fact.pop("entityId")
    fact.pop("id")
    fact["externalId"] = "f-amount"
    assert any(item["code"] == "INPUT_IDENTITY_INVALID"
               for item in validator(snap).check_path("facts.amount.value"))


def test_external_alias_cannot_supply_evidence_canonical_identity():
    snap = snapshot(evidence_rows=[{"externalId": "bank-flow", "type": "transaction_flow",
                                    "verificationStatus": "confirmed"}])
    v = validator(snap)
    assert v.check_path("facts.amount.value")
    assert v.summary()["status"] == "blocked"
    assert any(item["code"] == "INPUT_IDENTITY_INVALID"
               for item in validator(snap).check_path("entities.evidence.items.0"))


def test_id_only_legacy_identity_and_external_alias_remain_supported():
    snap = snapshot()
    fact = snap["items"][0]
    fact.pop("entityId")
    proof = snap["entities"]["evidence"][0]
    proof.pop("entityId")
    proof["id"] = "legacy-proof"
    assert validator(snap).check_path("facts.amount.value") == []
