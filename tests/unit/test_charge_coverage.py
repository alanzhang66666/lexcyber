import pytest

from engine.rules.charge_coverage import coverage_for_rules, parse_requested_charges


def test_missing_and_empty_requested_charges_are_compatible():
    assert parse_requested_charges(None) == ([], [])
    assert parse_requested_charges([]) == ([], [])


@pytest.mark.parametrize("raw", [
    {"requestedCharge": "x"},
    [{"requestedCharge": "x"}, {"requestedCharge": "x"}],
    [{"requestedCharge": "x", "chargeKey": "k"}, {"requestedCharge": "y", "chargeKey": "k"}],
    [{"requestedCharge": "x", "extra": True}],
])
def test_invalid_requested_charge_shapes_block(raw):
    _, blockers = parse_requested_charges(raw)
    assert blockers


def test_coverage_is_exact_and_returns_rule_provenance():
    requests, blockers = parse_requested_charges([
        {"requestedCharge": "原始罪名", "chargeKey": "charge.x"},
        {"requestedCharge": "未知", "chargeKey": None},
    ])
    assert not blockers
    checks, missing = coverage_for_rules(requests, [{
        "ruleId": "r1", "ruleVersion": "1", "contentHash": "h", "sourceIds": ["s"],
        "coverage": {"covers": ["charge.x"]},
    }], point="conduct", date="2024-01-01")
    assert checks[0]["covered"] is True
    assert checks[0]["rule_versions"][0]["ruleId"] == "r1"
    assert missing[0]["charge_key"] is None
