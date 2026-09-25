from typing import Any


def execute(payload: dict[str, Any]) -> dict[str, Any]:
    fragments: list[dict[str, Any]] = []
    for page in payload.get("pages") or []:
        page_number = int(page.get("page") or page.get("page_number") or 1)
        text = page.get("text") or ""
        cursor = 0
        for paragraph_number, block in enumerate([item for item in text.split("\n") if item.strip()], start=1):
            start = cursor
            end = start + len(block)
            fragments.append(
                {
                    "page": page_number,
                    "paragraph": paragraph_number,
                    "text": block.strip(),
                    "start": start,
                    "end": end,
                }
            )
            cursor = end + 1
    if not fragments and payload.get("text"):
        fragments.append({"page": 1, "paragraph": 1, "text": payload["text"], "start": 0, "end": len(payload["text"])})
    return {"fragments": fragments, "warnings": [] if fragments else ["no page text available to anchor"]}
