from typing import Any


def execute(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("text"):
        return {
            "text": payload["text"],
            "pages": payload.get("pages") or [{"page": 1, "text": payload["text"]}],
            "engine": "passthrough",
            "warnings": ["ocr engine is not configured; returning provided text"],
        }
    return {
        "text": "",
        "pages": [],
        "engine": "unavailable",
        "warnings": ["ocr engine is not configured; scanned images cannot be parsed in v0.2"],
    }
