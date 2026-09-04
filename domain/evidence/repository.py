from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from storage.postgres.repository import connection


def create_evidence(case_id: str | None, evidence_id: str, name: str, sha256: str | None = None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    item_id = uuid4()
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO evidence.items (id, case_id, evidence_id, name, sha256, metadata)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (item_id, case_id, evidence_id, name, sha256, Jsonb(metadata or {})),
        )
    return {"id": str(item_id), "evidence_id": evidence_id, "name": name, "sha256": sha256}
