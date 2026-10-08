from __future__ import annotations

from engine.rules.evidence import check_required_evidence


def _rule(*kinds: str, **extra):
    return {"ruleId": "rule-evidence-1", "requiredEvidenceKinds": list(kinds), **extra}


def _snapshot(*evidence):
    return {"entities": {"evidence": list(evidence)}}


def test_all_declared_kinds_match_confirmed_evidence():
    result = check_required_evidence(
        _rule("chat_record", "transaction_flow"),
        _snapshot(
            {"type": "chat_record", "entityId": "550e8400-e29b-41d4-a716-446655440000", "verificationStatus": "confirmed"},
            {"type": "transaction_flow", "id": "external-tx-1", "verificationStatus": "confirmed"},
        ),
    )
    assert result["missingKinds"] == []
    assert result["unconfirmedKinds"] == []
    assert result["matchedEvidenceIds"] == {
        "chat_record": ["550e8400-e29b-41d4-a716-446655440000"],
        "transaction_flow": ["external-tx-1"],
    }
    assert result["blockers"] == []
    assert set(result) == {
        "ruleId", "requiredKinds", "matchedEvidenceIds", "missingKinds",
        "unconfirmedKinds", "blockers",
    }


def test_missing_kind_is_blocked_and_path_is_evidence_container():
    result = check_required_evidence(_rule("chat_record", "timeline"), _snapshot(
        {"type": "chat_record", "id": "chat-1", "verificationStatus": "confirmed"},
    ))
    assert result["missingKinds"] == ["timeline"]
    assert any(item["code"] == "RULE_EVIDENCE_MISSING"
               and item["path"] == "rule-evidence-1.entities.evidence"
               for item in result["blockers"])


def test_candidate_rejected_and_unknown_do_not_replace_confirmed():
    for status, code in (("candidate", "RULE_EVIDENCE_UNCONFIRMED"),
                         ("rejected", "RULE_EVIDENCE_UNCONFIRMED"),
                         ("unknown", "RULE_EVIDENCE_UNCONFIRMED")):
        result = check_required_evidence(
            _rule("transaction_flow"),
            _snapshot({"type": "transaction_flow", "id": f"{status}-1", "verificationStatus": status}),
        )
        assert result["unconfirmedKinds"] == ["transaction_flow"]
        assert result["missingKinds"] == []
        assert any(item["code"] == code for item in result["blockers"])


def test_two_confirmed_items_of_one_kind_are_allowed():
    result = check_required_evidence(_rule("timeline"), _snapshot(
        {"type": "timeline", "id": "event-1", "verificationStatus": "confirmed"},
        {"type": "timeline", "entityId": "event-2", "verificationStatus": "confirmed"},
    ))
    assert result["matchedEvidenceIds"]["timeline"] == ["event-1", "event-2"]
    assert result["blockers"] == []


def test_no_required_kinds_does_not_require_an_evidence_container():
    result = check_required_evidence(_rule(), {"entities": {}})
    assert result["requiredKinds"] == []
    assert result["blockers"] == []


def test_malformed_requirement_and_evidence_containers_are_explicit_blockers():
    requirement = check_required_evidence(
        {"ruleId": "bad-rule", "requiredEvidenceKinds": "transaction_flow"},
        {"entities": {"evidence": []}},
    )
    assert requirement["blockers"][0]["code"] == "RULE_EVIDENCE_REQUIREMENTS_INVALID"
    assert requirement["blockers"][0]["path"] == "bad-rule.requiredEvidenceKinds"

    container = check_required_evidence(
        _rule("transaction_flow"),
        {"entities": {"evidence": {"type": "transaction_flow"}}},
    )
    assert any(item["code"] == "RULE_EVIDENCE_CONTAINER_INVALID" for item in container["blockers"])


def test_empty_kind_and_empty_identity_are_rejected():
    result = check_required_evidence(
        _rule("", "transaction_flow"),
        _snapshot(
            {"type": "transaction_flow", "entityId": "", "id": "", "verificationStatus": "confirmed"},
        ),
    )
    assert any(item["code"] == "RULE_EVIDENCE_REQUIREMENT_INVALID" for item in result["blockers"])
    assert result["unconfirmedKinds"] == ["transaction_flow"]
    assert any(item["code"] == "RULE_EVIDENCE_IDENTITY_INVALID" for item in result["blockers"])


def test_non_string_kind_is_rejected_without_becoming_a_requirement():
    result = check_required_evidence(
        _rule("transaction_flow", 42, None),
        _snapshot({"type": "transaction_flow", "id": "tx-1", "verificationStatus": "confirmed"}),
    )
    assert result["requiredKinds"] == ["transaction_flow"]
    assert sum(item["code"] == "RULE_EVIDENCE_REQUIREMENT_INVALID" for item in result["blockers"]) == 2


def test_malformed_evidence_item_is_explicitly_blocked():
    result = check_required_evidence(_rule("transaction_flow"), _snapshot("not-an-object"))
    assert any(item["code"] == "RULE_EVIDENCE_ITEM_INVALID" for item in result["blockers"])
    assert any(item["code"] == "RULE_EVIDENCE_MISSING" for item in result["blockers"])


def test_non_string_or_empty_evidence_type_is_invalid_and_never_matches():
    result = check_required_evidence(
        _rule("transaction_flow"),
        _snapshot(
            {"type": {}, "id": "dict-kind", "verificationStatus": "confirmed"},
            {"type": [], "id": "list-kind", "verificationStatus": "confirmed"},
            {"type": "", "id": "empty-kind", "verificationStatus": "confirmed"},
        ),
    )
    invalid = [item for item in result["blockers"] if item["code"] == "RULE_EVIDENCE_ITEM_INVALID"]
    assert len(invalid) == 3
    assert all(item["path"].endswith(".type") for item in invalid)
    assert result["matchedEvidenceIds"]["transaction_flow"] == []
    assert result["missingKinds"] == ["transaction_flow"]


def test_confirmed_evidence_with_empty_identity_cannot_pass():
    result = check_required_evidence(
        _rule("transaction_flow"),
        _snapshot({"type": "transaction_flow", "entityId": "", "id": "", "verificationStatus": "confirmed"}),
    )
    assert result["matchedEvidenceIds"]["transaction_flow"] == []
    assert result["unconfirmedKinds"] == ["transaction_flow"]
    assert any(item["code"] == "RULE_EVIDENCE_IDENTITY_INVALID" for item in result["blockers"])


def test_no_requirements_does_not_gate_malformed_or_absent_evidence():
    for snapshot in ({}, {"entities": {"evidence": "malformed"}}, {"entities": {"evidence": [None]}}):
        result = check_required_evidence(_rule(), snapshot)
        assert result["blockers"] == []
        assert result["missingKinds"] == []
        assert result["unconfirmedKinds"] == []
