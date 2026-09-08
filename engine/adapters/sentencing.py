from __future__ import annotations

from typing import Any


class SentencingUnavailable(Exception):
    code = "SENTENCING_UNAVAILABLE"

    def __init__(self, message: str = "sentencing calculation is not wired") -> None:
        super().__init__(message)


def calculate(payload: dict[str, Any]) -> dict[str, Any]:
    """Reserved for T3 calculate_sentencing(). Do not invent a range."""
    _ = payload
    raise SentencingUnavailable()


class SentencingRunner:
    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return calculate(payload)
