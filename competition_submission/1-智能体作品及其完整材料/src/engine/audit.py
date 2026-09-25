from typing import Any

from engine.store import record_skill_execution


class EngineSkillAuditSink:
    def record(self, event: dict[str, Any]) -> None:
        record_skill_execution(event)
