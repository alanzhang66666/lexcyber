from __future__ import annotations

from typing import Any, Protocol

from engine.adapters.document_render import DraftRenderRunner
from engine.adapters.module_analysis import ComplianceRunner, ConvictionRunner
from engine.adapters.sentencing import SentencingRunner
from engine.adapters.sentencing_v2 import SentencingV2Runner
from engine.document_parse import DocumentParseRunner
from engine.model_probe import ModelProbeRunner
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


class DispatchingWorkflowRunner:
    """Routes reserved task types by metadata.taskType; other tasks keep the configured runner."""

    def __init__(
        self,
        fallback: WorkflowRunner,
        parse_runner: DocumentParseRunner | None = None,
        probe_runner: ModelProbeRunner | None = None,
        sentencing_runner: SentencingRunner | None = None,
        compliance_runner: ComplianceRunner | None = None,
        conviction_runner: ConvictionRunner | None = None,
    ) -> None:
        self.fallback = fallback
        self.parse_runner = parse_runner or DocumentParseRunner()
        self.probe_runner = probe_runner or ModelProbeRunner()
        self.sentencing_runner = sentencing_runner or SentencingRunner()
        self.compliance_runner = compliance_runner or ComplianceRunner()
        self.conviction_runner = conviction_runner or ConvictionRunner()
        self.sentencing_v2_runner = SentencingV2Runner()
        self.draft_render_runner = DraftRenderRunner()

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        metadata = payload.get("metadata") or {}
        task_type = metadata.get("taskType")
        if task_type == "document.parse":
            return self.parse_runner.run(payload)
        if task_type == "model.probe":
            return self.probe_runner.run(payload)
        if task_type == "sentencing.calculate":
            # /v2 模块派发带不可变快照 → 注册表化量刑；旧 metadata 重放保留兼容
            if isinstance(metadata.get("factsSnapshot"), dict):
                return self.sentencing_v2_runner.run(payload)
            return self.sentencing_runner.run(payload)
        if task_type == "compliance.analyze":
            return self.compliance_runner.run(payload)
        if task_type == "conviction.analyze":
            return self.conviction_runner.run(payload)
        if task_type == "draft.render":
            return self.draft_render_runner.run(payload)
        return self.fallback.run(payload)


def build_runner() -> WorkflowRunner:
    fallback: WorkflowRunner = LangGraphWorkflowRunner() if settings.workflow_profile == "legal" else StubWorkflowRunner()
    return DispatchingWorkflowRunner(fallback)
