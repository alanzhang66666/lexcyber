from __future__ import annotations

import hashlib
import json
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
            INSERT INTO engine.executions(execution_id, task_id, request_id, result_id, result_version, result_type, contract_version, status, current_stage, input_hash, artifact_stream_id, input_snapshot_ref)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'queued', 'accepted', %s, %s, %s)
            ON CONFLICT (execution_id) DO NOTHING
            RETURNING execution_id, task_id, request_id, status, current_stage, result_id, result_version, result_type,
                      content_json, content_hash, error_code, error_message, retryable, result_json, updated_at, input_hash, enqueued_at,
                      fencing_token, completion_identity, output_hash, output_envelope
            """,
            (payload["execution_id"], payload["task_id"], payload["request_id"], payload["result_id"], payload["result_version"],
             payload.get("result_type", "workflow.output"), payload.get("contract_version", "public-api-0.8"), payload["input_hash"],
             payload.get("artifact_stream_id"), payload.get("input_snapshot_ref")),
        ).fetchone()
        if row is None:
            row = conn.execute(
                """
                SELECT execution_id, task_id, request_id, status, current_stage, result_id, result_version, result_type,
                       content_json, content_hash, error_code, error_message, retryable, result_json, updated_at, input_hash, enqueued_at,
                       fencing_token, completion_identity, output_hash, output_envelope
                FROM engine.executions WHERE execution_id = %s
                """,
                (payload["execution_id"],),
            ).fetchone()
        if row is None:
            raise RuntimeError("execution disappeared during idempotent insert")
    return _view(row)


def get_execution(execution_id: UUID) -> dict[str, Any] | None:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT execution_id, task_id, request_id, status, current_stage, result_id, result_version, result_type,
                   content_json, content_hash, error_code, error_message, retryable, result_json, updated_at, input_hash, enqueued_at,
                   fencing_token, completion_identity, output_hash, output_envelope
            FROM engine.executions WHERE execution_id = %s
            """,
            (execution_id,),
        ).fetchone()
    return _view(row) if row else None


def claim_enqueue(execution_id: UUID) -> bool:
    with connection() as conn:
        row = conn.execute(
            """
            UPDATE engine.executions
            SET enqueue_claim_until = now() + interval '30 seconds'
            WHERE execution_id=%s AND status='queued' AND enqueued_at IS NULL
              AND (enqueue_claim_until IS NULL OR enqueue_claim_until < now())
            RETURNING execution_id
            """,
            (execution_id,),
        ).fetchone()
    return row is not None


def mark_enqueued(execution_id: UUID) -> None:
    with connection() as conn:
        conn.execute("UPDATE engine.executions SET enqueued_at=now(), enqueue_claim_until=NULL, updated_at=now() WHERE execution_id=%s", (execution_id,))


def release_enqueue(execution_id: UUID, error: str) -> None:
    with connection() as conn:
        conn.execute("UPDATE engine.executions SET enqueue_claim_until=NULL, enqueue_last_error=%s, updated_at=now() WHERE execution_id=%s", (error[:2000], execution_id))


def mark_running(execution_id: UUID, owner: str, stage: str = "running") -> int | None:
    """Claim an execution and mint its fencing token (v1.3 §8.4).

    Returns the token on success, ``None`` when the execution was already claimed
    by a live worker. All subsequent writes must carry this token — a stale
    worker can neither move the stage, checkpoint, nor complete the execution.
    """
    with connection() as conn:
        row = conn.execute(
            """
            UPDATE engine.executions
            SET status='running', current_stage=%s, lease_owner=%s,
                lease_until=now() + interval '6 minutes',
                fencing_token=nextval('engine.fencing_token_seq'), updated_at=now()
            WHERE execution_id=%s AND (status='queued' OR (status='running' AND lease_until < now()))
            RETURNING fencing_token
            """,
            (stage, owner, execution_id),
        ).fetchone()
    return int(row[0]) if row is not None else None


def set_current_stage(execution_id: UUID, stage: str, fencing_token: int) -> None:
    with connection() as conn:
        conn.execute(
            "UPDATE engine.executions SET current_stage=%s, updated_at=now() WHERE execution_id=%s AND status='running' AND fencing_token=%s",
            (stage, execution_id, fencing_token),
        )


def save_checkpoint(execution_id: UUID, stage: str, state: dict[str, Any], sequence_no: int, fencing_token: int) -> None:
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO engine.stage_checkpoints(execution_id, stage, state_json, sequence_no)
            SELECT %s, %s, %s, %s
            WHERE EXISTS (SELECT 1 FROM engine.executions WHERE execution_id=%s AND fencing_token=%s)
            ON CONFLICT (execution_id, sequence_no) DO NOTHING
            """,
            (execution_id, stage, Jsonb(state), sequence_no, execution_id, fencing_token),
        )


def record_skill_execution(event: dict[str, Any]) -> None:
    parent = event.get("parent_execution_id")
    if not parent:
        return
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO engine.skill_executions(execution_id, skill_execution_id, skill_id, skill_version, status, input_hash, output_hash, payload_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (execution_id, skill_execution_id) DO UPDATE SET status=EXCLUDED.status, output_hash=EXCLUDED.output_hash, payload_json=EXCLUDED.payload_json
            """,
            (UUID(str(parent)), UUID(str(event["execution_id"])), event["skill_id"], event["skill_version"], event["status"], event.get("input_hash"), event.get("output_hash"), Jsonb(event)),
        )


def record_callback_failure(execution_id: UUID, message: str) -> None:
    with connection() as conn:
        row = conn.execute("SELECT request_id, task_id FROM engine.executions WHERE execution_id=%s", (execution_id,)).fetchone()
        if row is None:
            return
        conn.execute(
            "INSERT INTO engine.audit_events(request_id, task_id, execution_id, agent_name, payload_json) VALUES (%s, %s, %s, 'engine.callback', %s)",
            (str(row[0]) if row[0] is not None else None, row[1], execution_id, Jsonb({"error": message[:2000], "kind": "callback_delivery_failed"})),
        )


def complete_execution(
    execution_id: UUID,
    status: str,
    stage: str,
    fencing_token: int,
    result: Any = None,
    error_code: str | None = None,
    error_message: str | None = None,
    retryable: bool = False,
    owner: str = "",
    human_review_required: bool = False,
) -> bool:
    """Terminate an execution; returns False when the fencing token is stale.

    A stale worker may not mark the execution completed nor publish a result
    (v1.3 §8.4). ``human_review_required`` rides inside ``output_envelope`` —
    it is a review hint for the application layer, never an execution state.
    """
    content_json = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")) if result is not None else None
    content_hash = hashlib.sha256(content_json.encode("utf-8")).hexdigest() if content_json is not None else None
    envelope = None
    completion_identity = None
    if status == "completed":
        envelope = {"outcome_status": "calculated", "human_review_required": human_review_required}
        completion_identity = f"{owner}:{fencing_token}"
    with connection() as conn:
        row = conn.execute(
            """
            UPDATE engine.executions
            SET status=%s, current_stage=%s, result_json=%s, content_json=%s, content_hash=%s,
                output_hash=%s, output_envelope=%s, completion_identity=%s,
                error_code=%s, error_message=%s, retryable=%s,
                lease_owner=NULL, lease_until=NULL, updated_at=now()
            WHERE execution_id=%s AND fencing_token=%s AND status IN ('claimed','running')
            RETURNING execution_id
            """,
            (
                status, stage, Jsonb(result) if result is not None else None, content_json,
                content_hash, content_hash, Jsonb(envelope) if envelope is not None else None,
                completion_identity, error_code, error_message, retryable, execution_id, fencing_token,
            ),
        ).fetchone()
    return row is not None


def _view(row: tuple[Any, ...]) -> dict[str, Any]:
    keys = ["execution_id", "task_id", "request_id", "status", "current_stage", "result_id", "result_version", "result_type",
            "content_json", "content_hash", "error_code", "error_message", "retryable", "result_ref", "updated_at", "input_hash", "enqueued_at",
            "fencing_token", "completion_identity", "output_hash", "output_envelope"]
    return dict(zip(keys, row))
