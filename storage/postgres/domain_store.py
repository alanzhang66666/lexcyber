from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from storage.postgres.repository import connection


def create_case(title: str, jurisdiction: str | None = None, as_of_date: str | None = None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    case_id = uuid4()
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO cases.matters (id, title, jurisdiction, as_of_date, metadata)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (case_id, title, jurisdiction, as_of_date, Jsonb(metadata or {})),
        )
    return {"id": str(case_id), "title": title, "jurisdiction": jurisdiction, "as_of_date": as_of_date, "status": "open"}


def get_case(case_id: str) -> dict[str, Any] | None:
    with connection() as conn:
        row = conn.execute(
            "SELECT id, title, jurisdiction, as_of_date, status, summary, metadata, created_at FROM cases.matters WHERE id = %s",
            (UUID(case_id),),
        ).fetchone()
        parties = conn.execute("SELECT role, name FROM cases.parties WHERE case_id = %s", (UUID(case_id),)).fetchall()
    if not row:
        return None
    keys = ["id", "title", "jurisdiction", "as_of_date", "status", "summary", "metadata", "created_at"]
    result = dict(zip(keys, row))
    result["id"] = str(result["id"])
    result["parties"] = [{"role": role, "name": name} for role, name in parties]
    return result


def create_document(case_id: str | None, filename: str, content_type: str | None, storage_key: str | None, sha256: str | None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    document_id = uuid4()
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO documents.files (id, case_id, filename, content_type, storage_key, sha256, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (document_id, UUID(case_id) if case_id else None, filename, content_type, storage_key, sha256, Jsonb(metadata or {})),
        )
    return {"id": str(document_id), "case_id": case_id, "filename": filename, "status": "uploaded", "sha256": sha256}


def get_document(document_id: str) -> dict[str, Any] | None:
    with connection() as conn:
        row = conn.execute(
            "SELECT id, case_id, filename, content_type, storage_key, sha256, status, metadata FROM documents.files WHERE id = %s",
            (UUID(document_id),),
        ).fetchone()
        pages = conn.execute("SELECT page_number, text FROM documents.pages WHERE document_id = %s ORDER BY page_number", (UUID(document_id),)).fetchall()
    if not row:
        return None
    keys = ["id", "case_id", "filename", "content_type", "storage_key", "sha256", "status", "metadata"]
    result = dict(zip(keys, row))
    result["id"] = str(result["id"])
    result["case_id"] = str(result["case_id"]) if result["case_id"] else None
    result["pages"] = [{"page": page, "text": text} for page, text in pages]
    return result


def save_document_pages(document_id: str, pages: list[dict[str, Any]], status: str = "parsed") -> None:
    with connection() as conn:
        conn.execute("DELETE FROM documents.pages WHERE document_id = %s", (UUID(document_id),))
        for page in pages:
            conn.execute(
                "INSERT INTO documents.pages (id, document_id, page_number, text, metadata) VALUES (%s, %s, %s, %s, %s)",
                (uuid4(), UUID(document_id), int(page.get("page") or 1), page.get("text") or "", Jsonb(page)),
            )
        conn.execute("UPDATE documents.files SET status = %s WHERE id = %s", (status, UUID(document_id)))


def create_review(case_id: str | None, task_id: str | None, risk_level: str | None, reason: str | None, payload: dict[str, Any]) -> dict[str, Any]:
    review_id = uuid4()
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO review.requests (id, case_id, task_id, risk_level, reason, payload)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (review_id, case_id, task_id, risk_level, reason, Jsonb(payload)),
        )
    return {"id": str(review_id), "status": "pending", "risk_level": risk_level, "reason": reason}


def list_reviews(status: str | None = None) -> list[dict[str, Any]]:
    query = "SELECT id, case_id, task_id, status, risk_level, reason, created_at FROM review.requests"
    params: tuple[Any, ...] = ()
    if status:
        query += " WHERE status = %s"
        params = (status,)
    query += " ORDER BY created_at DESC"
    with connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [
        {"id": str(row[0]), "case_id": row[1], "task_id": row[2], "status": row[3], "risk_level": row[4], "reason": row[5], "created_at": row[6]}
        for row in rows
    ]


def get_review(review_id: str) -> dict[str, Any] | None:
    with connection() as conn:
        row = conn.execute(
            "SELECT id, case_id, task_id, status, risk_level, reason, payload, created_at FROM review.requests WHERE id = %s",
            (UUID(review_id),),
        ).fetchone()
    if not row:
        return None
    return {
        "id": str(row[0]),
        "case_id": row[1],
        "task_id": row[2],
        "status": row[3],
        "risk_level": row[4],
        "reason": row[5],
        "payload": row[6],
        "created_at": row[7],
    }


def decide_review(review_id: str, decision: str, actor: str | None = None, comment: str | None = None) -> dict[str, Any] | None:
    review = get_review(review_id)
    if not review:
        return None
    status = {"approve": "approved", "reject": "rejected", "request-retry": "retry_requested"}.get(decision, decision)
    with connection() as conn:
        conn.execute("UPDATE review.requests SET status = %s, updated_at = NOW() WHERE id = %s", (status, UUID(review_id)))
        conn.execute(
            "INSERT INTO review.decisions (id, review_id, decision, actor) VALUES (%s, %s, %s, %s)",
            (uuid4(), UUID(review_id), decision, actor),
        )
        if comment:
            conn.execute(
                "INSERT INTO review.comments (id, review_id, actor, body) VALUES (%s, %s, %s, %s)",
                (uuid4(), UUID(review_id), actor, comment),
            )
    review["status"] = status
    review["decision"] = decision
    return review
