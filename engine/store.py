from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from engine.settings import settings


@contextmanager
def connection() -> Iterator[psycopg.Connection[Any]]:
    conn = psycopg.connect(settings.engine_database_url, connect_timeout=2)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def create_execution(payload: dict[str, Any]) -> dict[str, Any]:
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO engine.executions(execution_id, task_id, contract_version, status, current_stage, input_hash)
            VALUES (%s, %s, %s, 'queued', 'accepted', %s)
            ON CONFLICT (execution_id) DO UPDATE SET updated_at = now()
            RETURNING execution_id, task_id, status, current_stage, error_code, result_json, updated_at
            """,
            (payload["execution_id"], payload["task_id"], payload.get("contract_version", "public-api-0.3"), payload["input_hash"]),
        ).fetchone()
    return _view(row)


def get_execution(execution_id: UUID) -> dict[str, Any] | None:
    with connection() as conn:
        row = conn.execute(
            "SELECT execution_id, task_id, status, current_stage, error_code, result_json, updated_at FROM engine.executions WHERE execution_id = %s",
            (execution_id,),
        ).fetchone()
    return _view(row) if row else None


def mark_running(execution_id: UUID, owner: str) -> None:
    with connection() as conn:
        conn.execute(
            "UPDATE engine.executions SET status='running', current_stage='running', lease_owner=%s, lease_until=now() + interval '15 seconds', updated_at=now() WHERE execution_id=%s AND status IN ('queued', 'running')",
            (owner, execution_id),
        )


def save_checkpoint(execution_id: UUID, stage: str, state: dict[str, Any], sequence_no: int) -> None:
    with connection() as conn:
        conn.execute(
            "INSERT INTO engine.stage_checkpoints(execution_id, stage, state_json, sequence_no) VALUES (%s, %s, %s, %s) ON CONFLICT (execution_id, sequence_no) DO NOTHING",
            (execution_id, stage, Jsonb(state), sequence_no),
        )


def complete_execution(execution_id: UUID, status: str, stage: str, result: Any = None, error_code: str | None = None, error_message: str | None = None) -> None:
    with connection() as conn:
        conn.execute(
            "UPDATE engine.executions SET status=%s, current_stage=%s, result_json=%s, error_code=%s, error_message=%s, lease_owner=NULL, lease_until=NULL, updated_at=now() WHERE execution_id=%s",
            (status, stage, Jsonb(result) if result is not None else None, error_code, error_message, execution_id),
        )


def _view(row: tuple[Any, ...]) -> dict[str, Any]:
    keys = ["execution_id", "task_id", "status", "current_stage", "error_code", "result_ref", "updated_at"]
    return dict(zip(keys, row))
