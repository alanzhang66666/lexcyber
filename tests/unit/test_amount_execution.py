"""Component-aware amounts reach real adapters and fail closed in the worker."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from engine import worker
from engine.adapters import document_render, module_analysis, sentencing_v2
from engine.rules.evaluator import AmountAggregationError, build_view


def _snapshot(parent_value):
    return {
        "items": [{"key": "upstream_crime_established", "value": True,
                   "verificationStatus": "confirmed"}],
        "entities": {
            "jurisdictionConnections": [{"verificationStatus": "confirmed"}],
            "amounts": [
                {"id": "child", "entityId": "22222222-2222-2222-2222-222222222222",
                 "kind": "payment_settlement_amount", "value": "80000",
                 "componentOf": "11111111-1111-1111-1111-111111111111",
                 "verificationStatus": "confirmed"},
                {"id": "parent", "entityId": "11111111-1111-1111-1111-111111111111",
                 "kind": "payment_settlement_amount", "value": str(parent_value),
                 "verificationStatus": "confirmed"},
            ],
        },
    }


@pytest.mark.parametrize("parent_value,severity_fired,months", [(120000, False, None), (250000, True, 12)])
def test_real_corpus_adapters_use_parent_total_once(monkeypatch, parent_value, severity_fired, months):
    # Registry reads are isolated; the predicates/calculation are repository
    # corpus code. This test does not create a real legal approval.
    corpus = json.loads((Path(__file__).resolve().parents[2] / "engine/rules/corpus/core_rules.json").read_text())
    rules = [{"family": r["family"], "ruleId": r["rule_id"], "ruleVersion": r["rule_version"],
              "predicate": r["predicate"], "outcome": r["outcome"],
              "sourceIds": [], "contentHash": "test"} for r in corpus["rules"]]
    monkeypatch.setattr(module_analysis.registry, "active_rules",
                        lambda family, *_: [r for r in rules if r["family"] == family])
    payload = {"case_id": str(uuid4()), "input_snapshot_ref": "facts_version:" + str(uuid4()),
               "metadata": {"asOfDate": "2026-01-01", "factsSnapshot": _snapshot(parent_value),
                            "artifactVersions": {"conviction": str(uuid4())}}}
    conviction = module_analysis.analyze(payload, "conviction.analyze")["final_output"]
    severity = next(r for r in conviction["rules"]
                    if r["ruleId"] == "rule-conviction-assist-severity-2019-threshold")
    assert severity["fired"] is severity_fired
    sentencing = sentencing_v2.calculate_v2(payload)["final_output"]
    assert sentencing["results"][0]["term_months"] == months
    if months is None:
        assert sentencing["status"] == "blocked"
    monkeypatch.setattr(document_render.registry, "active_template", lambda _: {
        "templateId": "component-test", "templateVersion": "1", "contentHash": "test",
        "bodyTemplate": "合计{{amounts.payment_settlement_amount.sum}}", "fieldSchema": {},
    })
    rendered = document_render.render({**payload, "metadata": {
        **payload["metadata"], "docType": "test", "artifacts": {}, "artifactVersions": {},
    }})["final_output"]
    assert rendered["status"] == "rendered" and rendered["body"] == f"合计{parent_value}"


@pytest.mark.parametrize("task_type", ["conviction.analyze", "compliance.analyze", "sentencing.calculate", "draft.render"])
def test_invalid_component_graph_has_nonretryable_failure_without_output(monkeypatch, task_type):
    snapshot = _snapshot(120000)
    snapshot["entities"]["amounts"][1]["componentOf"] = "22222222-2222-2222-2222-222222222222"
    completions, notifications = [], []
    monkeypatch.setattr(worker, "mark_running", lambda *args: 7)
    monkeypatch.setattr(worker, "build_runner", lambda: SimpleNamespace(run=lambda _: build_view(snapshot)))
    monkeypatch.setattr(worker, "complete_execution",
                        lambda *args, **kwargs: completions.append((args, kwargs)) or True)
    monkeypatch.setattr(worker, "_notify_application", notifications.append)
    execution_id = uuid4()
    with pytest.raises(AmountAggregationError):
        worker.run_execution({"execution_id": str(execution_id), "metadata": {"taskType": task_type}})
    assert len(completions) == 1
    args, kwargs = completions[0]
    assert args[0] == execution_id and args[1] == "failed" and args[3] == 7
    assert args[4] is None and args[5] == "AMOUNT_AGGREGATION_INVALID"
    assert kwargs["retryable"] is False and notifications == [execution_id]
