import importlib
import time
from typing import Any

from skill_runtime.registry import SkillRegistry
from skill_runtime.schemas import SkillRequest, SkillResult


class SkillExecutor:
    """Executes allowlisted, registered skills and returns a stable result contract."""

    def __init__(self, registry: SkillRegistry | None = None):
        self.registry = registry or SkillRegistry()

    def list_skills(self) -> list[dict[str, Any]]:
        return [manifest.model_dump() for manifest in self.registry.list()]

    def execute(self, request: SkillRequest) -> SkillResult:
        manifest = self.registry.get(request.skill_id, request.skill_version)
        self._validate_input(manifest.input_schema, request.input)
        started = time.perf_counter()
        try:
            module_name, function_name = manifest.entrypoint.split(":", maxsplit=1)
            if not module_name.startswith("skills.") or ".." in module_name:
                raise ValueError("skill entrypoint is outside the registered skills namespace")
            handler = getattr(importlib.import_module(module_name), function_name)
            output = handler(request.input)
            if not isinstance(output, dict):
                raise TypeError("skill handler must return a dictionary")
            return SkillResult(
                skill_id=manifest.id,
                skill_version=manifest.version,
                status="completed",
                output=output,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        except Exception as exc:
            return SkillResult(
                skill_id=manifest.id,
                skill_version=manifest.version,
                status="failed",
                duration_ms=int((time.perf_counter() - started) * 1000),
                error=str(exc),
            )

    @staticmethod
    def _validate_input(schema: dict[str, Any], payload: dict[str, Any]) -> None:
        missing = [name for name in schema.get("required", []) if name not in payload]
        if missing:
            raise ValueError(f"missing required skill input: {', '.join(missing)}")
