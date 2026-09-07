from __future__ import annotations

import base64
from collections.abc import Callable
from typing import Any

from engine.settings import settings
from skill_runtime.errors import SkillTimeoutError
from skill_runtime.timeout import run_with_timeout
from skills.common.document import parse_docx, parse_pdf

FetchBytes = Callable[[str], bytes]

FATAL_WARNING_MARKERS = (
    "parse failed",
    "no docx content supplied",
    "no pdf content supplied",
    "no docx bytes supplied",
    "no pdf bytes supplied",
)


class DocumentParseError(Exception):
    def __init__(self, message: str, code: str = "DOCUMENT_PARSE_FAILED") -> None:
        super().__init__(message)
        self.code = code


class DocumentParseRunner:
    """Loads stored file bytes and wraps T3 parse skills into document.parse.v1."""

    def __init__(
        self,
        fetch_bytes: FetchBytes | None = None,
        parse_docx_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        parse_pdf_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        self.fetch_bytes = fetch_bytes
        self.parse_docx_fn = parse_docx_fn or parse_docx.execute
        self.parse_pdf_fn = parse_pdf_fn or parse_pdf.execute
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else settings.document_parse_timeout_seconds

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        metadata = payload.get("metadata") or {}
        document_id = str(metadata.get("documentId") or metadata.get("document_id") or "")
        filename = str(metadata.get("filename") or "")
        content_type = str(metadata.get("contentType") or metadata.get("content_type") or "")
        storage_key = str(metadata.get("storageKey") or metadata.get("storage_key") or "")
        if not storage_key:
            raise DocumentParseError("missing storageKey for document.parse")

        data = self._load_bytes(storage_key)
        if not data:
            raise DocumentParseError("stored document is empty; refusing to parse without file bytes")

        fmt = _detect_format(filename, content_type, metadata)
        skill_payload = {
            "document_id": document_id,
            "filename": filename,
            "content_base64": base64.b64encode(data).decode("ascii"),
        }
        raw = self._execute(fmt, skill_payload)
        _raise_if_fatal(raw)
        return wrap_parse_result(raw, document_id=document_id, fmt=fmt)

    def _load_bytes(self, storage_key: str) -> bytes:
        fetch = self.fetch_bytes
        if fetch is None:
            from engine.object_store import fetch_object_bytes

            fetch = fetch_object_bytes
        try:
            return fetch(storage_key)
        except DocumentParseError:
            raise
        except Exception as exc:
            raise DocumentParseError(f"unable to read stored document: {exc}") from exc

    def _execute(self, fmt: str, skill_payload: dict[str, Any]) -> dict[str, Any]:
        handler = self.parse_pdf_fn if fmt == "pdf" else self.parse_docx_fn
        try:
            return run_with_timeout(handler, args=(skill_payload,), timeout_seconds=self.timeout_seconds)
        except SkillTimeoutError:
            raise
        except Exception as exc:
            raise DocumentParseError(f"无法解析该文件，请检查文件是否损坏或加密: {exc}") from exc


def wrap_parse_result(raw: dict[str, Any], document_id: str, fmt: str) -> dict[str, Any]:
    paragraphs = [_with_locator(item, "paragraph", item.get("paragraph")) for item in list(raw.get("paragraphs") or [])]
    tables = [_with_locator(item, "table", item.get("table")) for item in list(raw.get("tables") or [])]
    pages = [_with_locator(item, "page", item.get("page")) for item in list(raw.get("pages") or [])]
    if fmt == "docx":
        pages = []
    if fmt == "pdf":
        paragraphs = paragraphs or []
        tables = tables or []
    return {
        "schemaVersion": "document.parse.v1",
        "taskType": "document.parse",
        "documentId": document_id,
        "format": fmt,
        "text": raw.get("text") or "",
        "pages": pages,
        "paragraphs": paragraphs,
        "tables": tables,
        "warnings": list(raw.get("warnings") or []),
        "missing": list(raw.get("missing") or []),
        "errors": list(raw.get("errors") or []),
    }


def _detect_format(filename: str, content_type: str, metadata: dict[str, Any]) -> str:
    declared = str(metadata.get("format") or "").lower()
    if declared in {"pdf", "docx"}:
        return declared
    name = filename.lower()
    type_name = content_type.lower()
    if name.endswith(".pdf") or type_name == "application/pdf":
        return "pdf"
    return "docx"


def _with_locator(item: dict[str, Any], kind: str, number: Any) -> dict[str, Any]:
    result = dict(item)
    if not result.get("locator") and number not in (None, ""):
        result["locator"] = f"{kind}:{number}"
    return result


def _raise_if_fatal(raw: dict[str, Any]) -> None:
    warnings = [str(item).lower() for item in (raw.get("warnings") or [])]
    if any(marker in warning for warning in warnings for marker in FATAL_WARNING_MARKERS):
        raise DocumentParseError("无法解析该文件，请检查文件是否损坏或加密")
