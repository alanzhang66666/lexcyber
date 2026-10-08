from copy import deepcopy

import pytest

from engine.rules import registry
from scripts.ci_seed_registry import _candidate_path_rules


@pytest.mark.parametrize("outcome", [
    {"candidate_paths": None}, {"candidate_paths": []},
    {"candidate_paths": [None]}, {"candidate_paths": [{}]},
])
def test_invalid_path_plan_rejected_before_database(monkeypatch, outcome):
    monkeypatch.setattr(registry, "connection", lambda: pytest.fail("invalid plan must not access DB"))
    item = deepcopy(_candidate_path_rules("00000000-0000-0000-0000-000000000001")[0])
    item["outcome"] = outcome
    with pytest.raises(registry.RegistryError) as error:
        registry.register_rule_package(item)
    assert error.value.code == "INVALID_CONVICTION_PATH_PLAN"


@pytest.mark.parametrize("family, sources", [("compliance", ["source"]), ("conviction", [])])
def test_path_plan_requires_correct_family_and_source_binding(monkeypatch, family, sources):
    monkeypatch.setattr(registry, "connection", lambda: pytest.fail("invalid plan must not access DB"))
    item = deepcopy(_candidate_path_rules("00000000-0000-0000-0000-000000000001")[0])
    item["family"] = family
    item["source_ids"] = sources
    with pytest.raises(registry.RegistryError) as error:
        registry.register_rule_package(item)
    assert error.value.code == "INVALID_CONVICTION_PATH_PLAN"
