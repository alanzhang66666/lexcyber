import time
from contextlib import contextmanager
from typing import Any, Iterator
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb

from config.settings import settings


@contextmanager
def connection() -> Iterator[psycopg.Connection[Any]]:
    conn = psycopg.connect(settings.database_url, connect_timeout=2)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def wait_for_database(attempts: int = 30) -> None:
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            with connection() as conn:
                conn.execute("SELECT 1")
            return
        except Exception as exc:  # pragma: no cover - startup-only path
            last_error = exc
            time.sleep(1)
    raise RuntimeError("PostgreSQL is not available") from last_error


def init_db() -> None:
    wait_for_database()
    from skill_runtime.registry import load_catalog
    from storage.postgres.migrations import apply_migrations
    from storage.postgres.skill_store import upsert_skill_manifests

    apply_migrations()
    try:
        upsert_skill_manifests([item.model_dump() for item in load_catalog()])
    except Exception:
        pass


def create_task(user_query: str, session_id: str | None, metadata: dict[str, Any]) -> dict[str, Any]:
    task_id = uuid4()
    request_id = str(uuid4())
    session_id = session_id or str(uuid4())
    state = {"request_id": request_id, "session_id": session_id, "user_query": user_query, "metadata": metadata, "retry_count": 0}
    with connection() as conn:
        conn.execute(
            "INSERT INTO workflow.tasks (id, request_id, session_id, user_query, status, state_json) VALUES (%s, %s, %s, %s, %s, %s)",
            (task_id, request_id, session_id, user_query, "queued", Jsonb(state)),
        )
    return {"id": str(task_id), "request_id": request_id, "session_id": session_id, "status": "queued"}


def get_task(task_id: str) -> dict[str, Any] | None:
    with connection() as conn:
        row = conn.execute(
            "SELECT id, request_id, session_id, user_query, status, state_json, result_json, error, retry_count, created_at, updated_at FROM workflow.tasks WHERE id = %s",
            (UUID(task_id),),
        ).fetchone()
    if not row:
        return None
    keys = ["id", "request_id", "session_id", "user_query", "status", "state", "result", "error", "retry_count", "created_at", "updated_at"]
    result = dict(zip(keys, row))
    result["id"] = str(result["id"])
    return result


def update_task_state(task_id: str, state: dict[str, Any], status: str | None = None) -> None:
    with connection() as conn:
        if status:
            conn.execute("UPDATE workflow.tasks SET state_json=%s, status=%s, updated_at=NOW() WHERE id=%s", (Jsonb(state), status, UUID(task_id)))
        else:
            conn.execute("UPDATE workflow.tasks SET state_json=%s, updated_at=NOW() WHERE id=%s", (Jsonb(state), UUID(task_id)))


def save_checkpoint(task_id: str, node_name: str, state: dict[str, Any]) -> None:
    with connection() as conn:
        conn.execute("INSERT INTO workflow.checkpoints (task_id, node_name, state_json) VALUES (%s, %s, %s)", (UUID(task_id), node_name, Jsonb(state)))


def complete_task(task_id: str, state: dict[str, Any], status: str = "completed", error: str | None = None) -> None:
    with connection() as conn:
        conn.execute(
            "UPDATE workflow.tasks SET state_json=%s, result_json=%s, status=%s, error=%s, retry_count=%s, updated_at=NOW() WHERE id=%s",
            (Jsonb(state), Jsonb(state.get("final_output")), status, error, state.get("retry_count", 0), UUID(task_id)),
        )


def record_prompt(prompt_id: str, version: str, content: str, model_name: str) -> None:
    with connection() as conn:
        conn.execute(
            "INSERT INTO agent.prompt_versions (prompt_id, version, model_name, content) VALUES (%s, %s, %s, %s) ON CONFLICT (prompt_id, version) DO NOTHING",
            (prompt_id, version, model_name, content),
        )


def record_audit(event: dict[str, Any]) -> None:
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO audit.events (request_id, task_id, agent_name, model_name, prompt_version, input_hash, tool_calls, model_output, token_usage, latency_ms, reviewer_result)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (event["request_id"], event.get("task_id"), event["agent_name"], event.get("model_name"), event.get("prompt_version"), event.get("input_hash"), Jsonb(event.get("tool_calls", [])), Jsonb(event.get("model_output")), Jsonb(event.get("token_usage")), event.get("latency_ms"), event.get("reviewer_result")),
        )
