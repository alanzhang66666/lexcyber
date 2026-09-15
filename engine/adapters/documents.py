from __future__ import annotations

from pathlib import Path
from typing import Any

from skills.common.document.parse_docx import execute as parse_docx
from skills.common.document.parse_pdf import execute as parse_pdf


def parse_document(payload: dict[str, Any]) -> dict[str, Any]:
    """Parse one T1-owned document and preserve source locators.

    T1 supplies the real ``DocumentView.id`` and materialized content. The
    browser never supplies an object-storage key to this function.
    """

    document_id = str(payload.get("document_id") or payload.get("documentId") or "")
    filename = str(payload.get("filename") or "")
    if not document_id:
        raise ValueError("document_id is required")
    if not filename:
        raise ValueError("filename is required")
    if not any(payload.get(key) for key in ("content_base64", "text", "pages")):
        raise ValueError("one of content_base64, text, or pages is required")

    extension = Path(filename).suffix.lower()
    if extension == ".docx":
        raw = parse_docx(payload)
    elif extension == ".pdf":
        raw = parse_pdf(payload)
    else:
        raise ValueError(f"unsupported document type: {extension or '<missing>'}")

    paragraphs = [
        {
            **item,
            "locator": f"paragraph:{item['paragraph']}",
        }
        for item in raw.get("paragraphs", [])
    ]
    tables = [
        {
            **item,
            "locator": f"table:{item['table']}",
        }
        for item in raw.get("tables", [])
    ]
    pages = [
        {
            **item,
            "locator": f"page:{item['page']}",
        }
        for item in raw.get("pages", [])
    ]
    return {
        "schemaVersion": "document.parse.v1",
        "documentId": document_id,
        "paragraphs": paragraphs,
        "tables": tables,
        "pages": pages,
        "text": str(raw.get("text") or ""),
        "warnings": list(raw.get("warnings", [])),
    }
