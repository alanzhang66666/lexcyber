from __future__ import annotations

from typing import Any, Protocol

from engine.runners import DocumentParseRunner, SentencingRunner
from engine.settings import settings


class WorkflowRunner(Protocol):
    def run(self, payload: dict[str, Any]) -> dict[str, Any]: ...


class StubWorkflowRunner:
    """Deterministic generic runner used by the platform demo and CI."""

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        metadata = payload.get("metadata") or {}
        requires_review = bool(metadata.get("demo_requires_review"))
        status = "NEED_HUMAN" if requires_review else "PASS"
        return {
            "summary": str(payload.get("query") or ""),
            "status": status,
            "review_status": status,
            "human_approval_required": requires_review,
            "metadata_keys": sorted(str(key) for key in metadata),
            "runner": "stub",
        }


class LangGraphWorkflowRunner:
    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        from graph.workflow import build_workflow

        state = {
            "task_id": str(payload["task_id"]),
            "request_id": str(payload["request_id"]),
            "session_id": payload.get("session_id"),
            "user_query": payload["query"],
            "metadata": payload.get("metadata") or {},
            "case_id": payload.get("case_id"),
            "execution_id": str(payload["execution_id"]),
            "engine_mode": True,
        }
        return dict(build_workflow().invoke(state))


def _task_type(payload: dict[str, Any]) -> str:
    metadata = payload.get("metadata") or {}
    return str(metadata.get("task_type") or metadata.get("operation") or payload.get("result_type") or "")


def build_runner(payload: dict[str, Any] | None = None) -> WorkflowRunner:
    task_type = _task_type(payload or {})
    if task_type in {"document.parse", "document.parse.v1"}:
        return DocumentParseRunner()
    if task_type == "sentencing.calculate":
        return SentencingRunner()
    if settings.workflow_profile == "legal":
        return LangGraphWorkflowRunner()
    return StubWorkflowRunner()
