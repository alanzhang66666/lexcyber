import base64
import io
from typing import Any


def execute(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("pages"):
        pages = payload["pages"]
        return {"pages": pages, "page_count": len(pages), "text": "\n".join(page.get("text", "") for page in pages), "warnings": []}
    text = payload.get("text")
    content = payload.get("content_base64")
    pages: list[dict[str, Any]] = []
    warnings: list[str] = []
    if content:
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(base64.b64decode(content)))
            for index, page in enumerate(reader.pages, start=1):
                extracted = page.extract_text() or ""
                pages.append({"page": index, "text": extracted, "width": float(page.mediabox.width), "height": float(page.mediabox.height)})
        except Exception as exc:
            warnings.append(f"pdf parse failed: {exc}")
    elif text:
        pages = [{"page": 1, "text": text, "width": None, "height": None}]
        warnings.append("no pdf bytes supplied; using provided text as page 1")
    else:
        warnings.append("no pdf content supplied")
    combined = "\n".join(page.get("text", "") for page in pages)
    return {
        "pages": pages,
        "page_count": len(pages),
        "text": combined,
        "metadata": {"document_id": payload.get("document_id"), "filename": payload.get("filename")},
        "warnings": warnings,
    }
