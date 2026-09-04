from typing import Any

from storage.postgres.domain_store import create_document, get_document, save_document_pages


def register_document(case_id: str | None, filename: str, content_type: str | None, storage_key: str | None, sha256: str | None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return create_document(case_id, filename, content_type, storage_key, sha256, metadata)


def load_document(document_id: str) -> dict[str, Any] | None:
    return get_document(document_id)


def persist_pages(document_id: str, pages: list[dict[str, Any]]) -> None:
    save_document_pages(document_id, pages)
