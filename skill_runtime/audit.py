import hashlib
import json
from typing import Any

from skill_runtime.schemas import SkillRequest, SkillResult


def stable_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def execution_record(request: SkillRequest, result: SkillResult) -> dict[str, Any]:
    return {
        "execution_id": result.execution_id,
        "request_id": result.request_id or request.request_id,
        "case_id": result.case_id or request.case_id,
        "skill_id": result.skill_id,
        "skill_version": result.skill_version,
        "actor": result.actor or request.actor,
        "input_hash": result.input_hash or stable_hash(request.input),
        "output_hash": result.output_hash,
        "permission_result": result.permission_result,
        "source_ids": result.source_ids,
        "started_at": result.started_at,
        "ended_at": result.finished_at,
        "status": result.status,
        "error_code": result.error_code,
        "error": result.error,
        "model_usage": result.model_usage,
        "human_approval": result.human_approval,
        "output": result.output,
        "warnings": result.warnings,
        "duration_ms": result.duration_ms,
    }


class SkillAuditSink:
    def record(self, event: dict[str, Any]) -> None:
        raise NotImplementedError


class InMemoryAuditSink(SkillAuditSink):
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def record(self, event: dict[str, Any]) -> None:
        self.events.append(event)


class PostgresAuditSink(SkillAuditSink):
    def record(self, event: dict[str, Any]) -> None:
        try:
            from storage.postgres.skill_store import record_skill_execution

            record_skill_execution(event)
        except Exception:
            return


def default_sink() -> SkillAuditSink:
    return PostgresAuditSink()
