"""Isolated 0.8 entry point: broker and audit bridge are installed first."""

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from psycopg.types.json import Jsonb

import audit.logger as legacy_audit
from engine.settings import settings
from engine.store import connection


def record_engine_audit(event: dict) -> None:
    with connection() as conn:
        conn.execute(
            "INSERT INTO engine.audit_events(request_id, execution_id, agent_name, payload_json) VALUES (%s, %s, %s, %s)",
            (event.get("request_id"), event.get("execution_id"), event.get("agent_name", "unknown"), Jsonb(event)),
        )


legacy_audit.record_audit = record_engine_audit
dramatiq.set_broker(RedisBroker(url=settings.redis_url))

from engine.api import app  # noqa: E402

__all__ = ["app"]
