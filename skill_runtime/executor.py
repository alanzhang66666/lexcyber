import importlib
import time
from typing import Any

from skill_runtime.audit import InMemoryAuditSink, SkillAuditSink, default_sink, execution_record, stable_hash
from skill_runtime.errors import (
    SkillEntrypointError,
    SkillHandlerError,
    SkillNeedHumanError,
    SkillNotFoundError,
    SkillPermissionError,
    SkillProhibitedError,
    SkillRuntimeError,
    SkillTimeoutError,
    SkillValidationError,
)
from skill_runtime.policy import evaluate
from skill_runtime.registry import SkillRegistry
from skill_runtime.schemas import SkillRequest, SkillResult, utcnow
from skill_runtime.timeout import run_with_timeout
from skill_runtime.validator import validate_payload


class SkillExecutor:
    """Executes allowlisted, registered skills and returns a stable result contract."""

    def __init__(self, registry: SkillRegistry | None = None, audit_sink: SkillAuditSink | None = None):
        self.registry = registry or SkillRegistry()
        self.audit_sink = audit_sink or default_sink()
        self._idempotency_cache: dict[str, SkillResult] = {}

    def list_skills(self) -> list[dict[str, Any]]:
        return [manifest.model_dump() for manifest in self.registry.list()]

    def execute(self, request: SkillRequest) -> SkillResult:
        if request.idempotency_key and request.idempotency_key in self._idempotency_cache:
            return self._idempotency_cache[request.idempotency_key]

        started = time.perf_counter()
        started_at = utcnow().isoformat()
        skill_id = request.skill_id
        skill_version = request.skill_version or "unknown"
        try:
            manifest = self.registry.get(request.skill_id, request.skill_version)
            skill_id = manifest.id
            skill_version = manifest.version
            validate_payload(manifest.input_schema, request.input)
            decision = evaluate(manifest, request)
            output = self._invoke(manifest.callable_path, request.input, manifest.timeout_seconds)
            if not isinstance(output, dict):
                raise SkillHandlerError("skill handler must return a dictionary")
            validate_payload(manifest.output_schema, output, output=True)
            warnings = list(output.get("warnings") or [])
            warnings.extend(decision.reasons)
            citations = list(output.get("citations") or [])
            result = SkillResult(
                skill_id=manifest.id,
                skill_version=manifest.version,
                status="completed",
                output=output,
                citations=citations,
                warnings=warnings,
                permission_result=decision.permission_result,
                input_hash=stable_hash(request.input),
                output_hash=stable_hash(output),
                source_ids=[item.get("source_id") for item in citations if isinstance(item, dict) and item.get("source_id")],
                actor=request.actor,
                case_id=request.case_id,
                request_id=request.request_id,
                human_approval=request.human_approved,
                started_at=started_at,
                duration_ms=int((time.perf_counter() - started) * 1000),
            ).mark_finished()
        except SkillRuntimeError as exc:
            result = SkillResult(
                skill_id=skill_id,
                skill_version=skill_version,
                status=getattr(exc, "status", "failed"),
                error=str(exc),
                error_code=exc.code,
                permission_result="denied" if isinstance(exc, (SkillPermissionError, SkillProhibitedError, SkillNeedHumanError)) else "error",
                input_hash=stable_hash(request.input),
                actor=request.actor,
                case_id=request.case_id,
                request_id=request.request_id,
                human_approval=request.human_approved,
                started_at=started_at,
                duration_ms=int((time.perf_counter() - started) * 1000),
            ).mark_finished()
        except Exception as exc:
            wrapped = SkillHandlerError(str(exc))
            result = SkillResult(
                skill_id=skill_id,
                skill_version=skill_version,
                status="failed",
                error=str(wrapped),
                error_code=wrapped.code,
                permission_result="error",
                input_hash=stable_hash(request.input),
                actor=request.actor,
                case_id=request.case_id,
                request_id=request.request_id,
                started_at=started_at,
                duration_ms=int((time.perf_counter() - started) * 1000),
            ).mark_finished()

        self.audit_sink.record(execution_record(request, result))
        if request.idempotency_key:
            self._idempotency_cache[request.idempotency_key] = result
        return result

    def _invoke(self, callable_path: str, payload: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
        if ":" not in callable_path:
            raise SkillEntrypointError("skill handler must be module:function")
        module_name, function_name = callable_path.split(":", maxsplit=1)
        if not module_name.startswith("skills.") or ".." in module_name:
            raise SkillEntrypointError("skill handler is outside the registered skills namespace")
        try:
            handler = getattr(importlib.import_module(module_name), function_name)
        except Exception as exc:
            raise SkillEntrypointError(f"unable to load skill handler {callable_path}") from exc
        try:
            return run_with_timeout(handler, args=(payload,), timeout_seconds=timeout_seconds)
        except SkillTimeoutError:
            raise
        except SkillValidationError:
            raise
        except Exception as exc:
            raise SkillHandlerError(str(exc)) from exc


# Re-export lookup error for existing imports.
SkillNotFoundError = SkillNotFoundError
InMemoryAuditSink = InMemoryAuditSink
