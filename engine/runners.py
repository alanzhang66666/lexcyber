from __future__ import annotations

from typing import Any

from engine.adapters.case_bundle import load_case_bundle
from engine.adapters.documents import parse_document
from engine.adapters.sentencing import calculate_case_sentencing, calculate_sentencing
from engine.adapters.t1_contract import map_sentencing_result_to_t1


class RunnerInputError(ValueError):
    """Non-retryable task input error with a stable T1-facing envelope."""

    def __init__(self, code: str, path: str, message: str):
        super().__init__(message)
        self.code = code
        self.path = path
        self.message = message

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "path": self.path,
            "message": self.message,
            "retryable": False,
        }


def _metadata_input(payload: dict[str, Any], key: str) -> dict[str, Any]:
    metadata = payload.get("metadata") or {}
    value = metadata.get(key)
    if not isinstance(value, dict):
        raise RunnerInputError("runner_input_missing", f"metadata.{key}", f"metadata.{key} must be an object")
    return value


class DocumentParseRunner:
    """Runner for T1's automatically-created ``document.parse`` task."""

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        document = _metadata_input(payload, "document")
        try:
            result = parse_document(document)
        except ValueError as exc:
            raise RunnerInputError("document_parse_input_invalid", "metadata.document", str(exc)) from exc
        return {"final_output": result, "human_approval_required": False}


class SentencingRunner:
    """Runner for fail-closed ``sentencing.calculate`` execution tasks."""

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        server_case_id = str(payload.get("case_id") or "")
        if not server_case_id:
            raise RunnerInputError("case_id_missing", "case_id", "T1 CaseView.id is required")
        sentencing = _metadata_input(payload, "sentencing")
        dataset_case_id = str(sentencing.get("dataset_case_id") or sentencing.get("datasetCaseId") or "")
        actor_id = str(sentencing.get("actor_id") or sentencing.get("actorId") or "")
        if not dataset_case_id:
            raise RunnerInputError(
                "dataset_case_id_missing",
                "metadata.sentencing.datasetCaseId",
                "T3 dataset case id is required",
            )
        if not actor_id:
            raise RunnerInputError("actor_id_missing", "metadata.sentencing.actorId", "actor id is required")

        if "rule" in sentencing or "parameters" in sentencing:
            result = calculate_sentencing(
                {
                    "case_id": dataset_case_id,
                    "actor_id": actor_id,
                    "parameters": sentencing.get("parameters", []),
                    "rule": sentencing.get("rule", {}),
                }
            )
        else:
            try:
                bundle = load_case_bundle(dataset_case_id)
            except KeyError as exc:
                raise RunnerInputError(
                    "sentencing_case_unsupported",
                    "metadata.sentencing.datasetCaseId",
                    dataset_case_id,
                ) from exc
            result = calculate_case_sentencing(bundle, actor_id)

        mapped = map_sentencing_result_to_t1(result, case_id=server_case_id)
        return {
            "final_output": mapped["content"],
            "human_approval_required": mapped["taskStatus"] == "waiting_review",
        }
