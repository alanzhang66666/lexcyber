import re
from typing import Any

from skills.shared import warning_list

PATTERNS = {
    "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    "phone": r"(?<!\d)1[3-9]\d{9}(?!\d)",
    "identity_number": r"(?<![0-9Xx])\d{17}[0-9Xx](?![0-9Xx])",
}


def execute(payload: dict[str, Any]) -> dict[str, Any]:
    text = payload["text"]
    replacement = payload.get("replacement", "[REDACTED]")
    redactions: list[dict[str, Any]] = []
    redacted = text
    for kind, pattern in PATTERNS.items():
        for match in re.finditer(pattern, redacted):
            redactions.append({"type": kind, "value": match.group(), "start": match.start(), "end": match.end()})
        redacted = re.sub(pattern, replacement, redacted)
    warnings = warning_list(
        "pattern-based redaction is not a complete privacy review",
        "address, bank account, and trade-secret fields are not covered",
    ) if redactions else []
    return {"text": redacted, "redactions": redactions, "warnings": warnings}
