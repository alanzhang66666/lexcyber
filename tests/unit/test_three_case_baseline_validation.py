import json
import shutil
from pathlib import Path

import pytest

from engine.adapters.case_bundle import DEMO_ROOT, validate_three_case_baseline


@pytest.fixture
def dataset_root(tmp_path):
    root = tmp_path / "dataset"
    shutil.copytree(DEMO_ROOT, root)
    return root


def rewrite(path: Path, change):
    document = json.loads(path.read_text(encoding="utf-8"))
    change(document)
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")


def change_scenario(root, case_position, scenario_position, path, value):
    def change(document):
        target = document["cases"][case_position]["scenarios"][scenario_position]
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
    rewrite(root / "baseline-scenarios.json", change)


@pytest.mark.parametrize(("case_position", "scenario_position", "path", "value"), [
    pytest.param(0, 1, ("mutations",), [], id="missing-evidence-without-removal"),
    pytest.param(1, 1, ("mutations",), [], id="conflict-without-fact"),
    pytest.param(0, 0, ("expected", "analysis_status"), "blocked", id="normal-analysis-blocked"),
    pytest.param(0, 1, ("expected", "analysis_status"), "calculated", id="negative-analysis-calculated"),
    pytest.param(0, 1, ("expected", "blockers", 0, "code"), "FACT_CONFLICTED", id="wrong-blocker-code"),
    pytest.param(0, 1, ("expected", "blockers", 0, "subject_id"), "nonexistent-fact", id="unknown-blocker-fact"),
    pytest.param(0, 1, ("expected", "blockers", 0, "subject_id"), "fact-a-help", id="unrelated-blocker-fact"),
    pytest.param(0, 1, ("actor_id",), "actor-a-liang", id="mutation-belongs-to-another-actor"),
    pytest.param(0, 1, ("mutations", 0, "evidence_id"), "ev-a-01", id="unrelated-evidence"),
    pytest.param(0, 1, ("mutations", 0, "fact_id"), "nonexistent-fact", id="unknown-mutation-fact"),
    pytest.param(1, 1, ("mutations", 0, "fact_id"), "fact-b-042-provide-instruments", id="unconflicted-mutation-fact"),
])
def test_scenario_rejects_inconsistent_operations_and_expectations(
    dataset_root, case_position, scenario_position, path, value,
):
    change_scenario(dataset_root, case_position, scenario_position, path, value)
    result = validate_three_case_baseline(dataset_root)
    assert not result["valid"], result
    assert result["errors"]


def test_conflict_path_cannot_be_relabelled_as_evidence_removal(dataset_root):
    change_scenario(dataset_root, 1, 1, ("mutations",), [{
        "operation": "remove_evidence", "fact_id": "fact-b-042-knowledge", "evidence_id": "ev-b-042-01",
    }])
    assert not validate_three_case_baseline(dataset_root)["valid"]


@pytest.mark.parametrize("include_second_blocker", [False, True])
def test_blockers_must_cover_every_mutated_fact(dataset_root, include_second_blocker):
    def change(document):
        scenario = document["cases"][0]["scenarios"][1]
        scenario["mutations"].append({
            "operation": "remove_evidence", "fact_id": "fact-a-help", "evidence_id": "ev-a-04",
        })
        if include_second_blocker:
            scenario["expected"]["blockers"].append({
                "code": "EVIDENCE_MISSING", "subject_id": "fact-a-help", "reason": "Removed supporting evidence",
            })
    rewrite(dataset_root / "baseline-scenarios.json", change)
    result = validate_three_case_baseline(dataset_root)
    assert result["valid"] is include_second_blocker, result
    expected_codes = set() if include_second_blocker else {"baseline_blocker_mutation_mismatch"}
    assert {error["code"] for error in result["errors"]} == expected_codes


def test_duplicate_blockers_are_rejected(dataset_root):
    def change(document):
        blockers = document["cases"][0]["scenarios"][1]["expected"]["blockers"]
        blockers.append(dict(blockers[0]))
    rewrite(dataset_root / "baseline-scenarios.json", change)
    result = validate_three_case_baseline(dataset_root)
    assert not result["valid"], result
    assert {error["code"] for error in result["errors"]} == {"baseline_blocker_mutation_mismatch"}


def change_conduct_period(root, code, period):
    index = json.loads((root / "index.json").read_text(encoding="utf-8"))
    bundle_path = next(item["bundle"] for item in index["cases"] if item["case_code"] == code)
    rewrite(root / bundle_path, lambda bundle: bundle.update(conduct_period=period))


def test_future_source_cannot_be_promoted_by_changing_scope_label(dataset_root):
    def change(document):
        binding = document["cases"][2]["source_bindings"][-1]
        binding.update(use_scope="conduct_time", applicable_to_conduct=True, application_time="2020-10")
    rewrite(dataset_root / "baseline-scenarios.json", change)
    result = validate_three_case_baseline(dataset_root)
    assert not result["valid"], result
    assert "baseline_source_outside_conduct_period" in {error["code"] for error in result["errors"]}


@pytest.mark.parametrize("period", [
    pytest.param({"start": "2020-01-01", "end": "2024-06-15"}, id="before-effective-start"),
    pytest.param({"start": "2024-05-08", "end": "2026-01-01"}, id="after-effective-end"),
    pytest.param({"start": "2024-05-08", "end": None}, id="unknown-end-with-expiring-source"),
])
def test_source_must_cover_entire_known_conduct_period(dataset_root, period):
    change_conduct_period(dataset_root, "B", period)
    result = validate_three_case_baseline(dataset_root)
    assert not result["valid"], result
    assert "baseline_source_outside_conduct_period" in {error["code"] for error in result["errors"]}


@pytest.mark.parametrize("period", [
    None,
    {},
    {"start": "invalid-date", "end": "2024-08-20"},
    {"start": "2024-03-15", "end": "invalid-date"},
    {"start": "2024-08-20", "end": "2024-03-15"},
])
def test_missing_or_malformed_conduct_period_is_reported(dataset_root, period):
    change_conduct_period(dataset_root, "A", period)
    result = validate_three_case_baseline(dataset_root)
    assert not result["valid"], result
    assert "baseline_conduct_period_invalid" in {error["code"] for error in result["errors"]}


def test_effective_dates_are_inclusive_and_audit_sources_stay_non_applicable(dataset_root):
    change_conduct_period(dataset_root, "B", {"start": "2021-04-15", "end": "2025-08-25"})
    result = validate_three_case_baseline(dataset_root)
    assert result["valid"], result["errors"]


def test_invalid_baseline_shape_returns_schema_errors(dataset_root):
    rewrite(dataset_root / "baseline-scenarios.json", lambda document: document.update(cases=None))
    result = validate_three_case_baseline(dataset_root)
    assert not result["valid"]
    assert any(error["code"] == "schema_validation_failed" for error in result["errors"])


@pytest.mark.parametrize("document", [None, []])
def test_non_object_baseline_returns_schema_errors(dataset_root, document):
    (dataset_root / "baseline-scenarios.json").write_text(json.dumps(document), encoding="utf-8")
    result = validate_three_case_baseline(dataset_root)
    assert not result["valid"]
    assert all(error["code"] == "schema_validation_failed" for error in result["errors"])
