from typing import Any


def location(*, page: int | None = None, start: int | None = None, end: int | None = None, line: int | None = None, paragraph: int | None = None) -> dict[str, Any]:
    return {"page": page, "start": start, "end": end, "line": line, "paragraph": paragraph}


def warning_list(*items: str) -> list[str]:
    return [item for item in items if item]
