import hashlib
import json
import time
from contextlib import contextmanager
from typing import Any, Iterator

from storage.postgres.repository import record_audit


def input_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


@contextmanager
def audit_event(state: dict[str, Any], agent_name: str, **extra: Any) -> Iterator[dict[str, Any]]:
    started = time.perf_counter()
    event = {"request_id": state.get("request_id", "unknown"), "task_id": state.get("task_id"), "agent_name": agent_name, "input_hash": input_hash(state.get("user_query", "")), **extra}
    try:
        yield event
    finally:
        event["latency_ms"] = int((time.perf_counter() - started) * 1000)
        try:
            record_audit(event)
        except Exception:
            pass
