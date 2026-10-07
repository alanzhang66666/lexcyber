"""Malformed frozen legal dates must fail without a result or an automatic retry."""
from uuid import uuid4

import pytest

from engine import worker
from engine.adapters.module_analysis import ModuleAnalysisError
from engine.rules import registry


@pytest.mark.parametrize("task_type", ["compliance.analyze", "conviction.analyze", "sentencing.calculate", "draft.render"])
def test_bad_date_is_nonretryable_and_never_reads_rules(monkeypatch, task_type):
    completed, callbacks = [], []
    monkeypatch.setattr(worker, "mark_running", lambda *args: 7)
    def complete(execution_id, status, stage, fencing_token, output, code, message, *, owner, retryable):
        completed.append(((execution_id, status, stage, fencing_token, output, code, message),
                          {"owner": owner, "retryable": retryable}))
        return True
    monkeypatch.setattr(worker, "complete_execution", complete)
    monkeypatch.setattr(worker, "_notify_application", callbacks.append)
    monkeypatch.setattr(registry, "active_rules", lambda *args: pytest.fail("invalid date must not query rules"))
    execution_id = uuid4()
    with pytest.raises(ModuleAnalysisError) as error:
        worker.run_execution({"execution_id": str(execution_id), "query": "test", "metadata": {
            "taskType": task_type, "asOfDate": "2024-02-30", "factsSnapshot": {"items": []},
            "artifactVersions": {"conviction": str(uuid4())}, "docType": "fixture",
        }})
    assert error.value.code == "INVALID_AS_OF_DATE"
    assert len(completed) == 1
    args, kwargs = completed[0]
    assert args[3] == 7 and args[1] == "failed" and args[4] is None and args[5] == "INVALID_AS_OF_DATE"
    assert kwargs["retryable"] is False and callbacks == [execution_id]
