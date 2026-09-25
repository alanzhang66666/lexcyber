from datetime import datetime
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from storage.postgres.repository import connection


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def upsert_skill_manifests(manifests: list[dict[str, Any]]) -> None:
    with connection() as conn:
        for manifest in manifests:
            conn.execute(
                """
                INSERT INTO skill.definitions (skill_id, name, category, description)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (skill_id) DO UPDATE SET name = EXCLUDED.name, category = EXCLUDED.category, description = EXCLUDED.description
                """,
                (manifest["id"], manifest["name"], manifest.get("category"), manifest.get("description")),
            )
            handler = manifest.get("handler") or manifest.get("entrypoint")
            conn.execute(
                """
                INSERT INTO skill.versions (
                  skill_id, version, status, risk_level, kind, handler, manifest, input_schema, output_schema, permissions, timeout_seconds, activated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (skill_id, version) DO UPDATE SET
                  status = EXCLUDED.status,
                  risk_level = EXCLUDED.risk_level,
                  handler = EXCLUDED.handler,
                  manifest = EXCLUDED.manifest,
                  input_schema = EXCLUDED.input_schema,
                  output_schema = EXCLUDED.output_schema,
                  permissions = EXCLUDED.permissions,
                  timeout_seconds = EXCLUDED.timeout_seconds
                """,
                (
                    manifest["id"],
                    manifest["version"],
                    "active" if manifest.get("enabled", True) else "disabled",
                    manifest.get("risk_level", "low"),
                    manifest.get("kind", "python"),
                    handler,
                    Jsonb(manifest),
                    Jsonb(manifest.get("input_schema", {})),
                    Jsonb(manifest.get("output_schema", {})),
                    Jsonb(manifest.get("permissions", [])),
                    manifest.get("timeout_seconds", 30),
                ),
            )


def record_skill_execution(event: dict[str, Any]) -> None:
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO skill.executions (
              execution_id, request_id, case_id, skill_id, skill_version, actor, input_hash, output_hash,
              permission_result, source_ids, status, error_code, error, model_usage, human_approval,
              started_at, ended_at, duration_ms, output, warnings
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (execution_id) DO UPDATE SET
              status = EXCLUDED.status,
              error_code = EXCLUDED.error_code,
              ended_at = EXCLUDED.ended_at,
              output = EXCLUDED.output
            """,
            (
                UUID(str(event["execution_id"])),
                event.get("request_id"),
                event.get("case_id"),
                event["skill_id"],
                event["skill_version"],
                event.get("actor"),
                event.get("input_hash"),
                event.get("output_hash"),
                event.get("permission_result"),
                Jsonb(event.get("source_ids", [])),
                event["status"],
                event.get("error_code"),
                event.get("error"),
                Jsonb(event.get("model_usage")),
                bool(event.get("human_approval")),
                _parse_time(event.get("started_at")),
                _parse_time(event.get("ended_at")),
                event.get("duration_ms"),
                Jsonb(event.get("output")),
                Jsonb(event.get("warnings", [])),
            ),
        )
        conn.execute(
            "INSERT INTO skill.execution_events (execution_id, event_type, payload) VALUES (%s, %s, %s)",
            (UUID(str(event["execution_id"])), event["status"], Jsonb(event)),
        )


def get_skill_execution(execution_id: str) -> dict[str, Any] | None:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT execution_id, skill_id, skill_version, status, output, warnings, error_code, error, duration_ms, started_at, ended_at
            FROM skill.executions WHERE execution_id = %s
            """,
            (UUID(execution_id),),
        ).fetchone()
    if not row:
        return None
    keys = ["execution_id", "skill_id", "skill_version", "status", "output", "warnings", "error_code", "error", "duration_ms", "started_at", "ended_at"]
    result = dict(zip(keys, row))
    result["execution_id"] = str(result["execution_id"])
    return result
