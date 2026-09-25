from typing import Any


def echo(payload: dict[str, Any]) -> dict[str, Any]:
    return {"status": "completed", "echo": payload.get("text", ""), "runner": "core.stub"}
