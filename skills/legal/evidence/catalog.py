import hashlib
from typing import Any

from skills.shared import warning_list


def execute(payload: dict[str, Any]) -> dict[str, Any]:
    items = payload.get("items", payload.get("evidence", []))
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        current = {"name": item} if isinstance(item, str) else dict(item)
        current.setdefault("evidence_id", f"E-{index:04d}")
        current.setdefault("confidence", 0.9)
        if current.get("content") and not current.get("sha256"):
            current["sha256"] = hashlib.sha256(str(current["content"]).encode("utf-8")).hexdigest()
        normalized.append(current)
    return {"items": normalized, "warnings": warning_list() if normalized else ["no evidence items supplied"]}
