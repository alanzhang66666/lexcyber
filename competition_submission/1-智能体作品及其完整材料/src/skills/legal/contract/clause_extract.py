import re
from typing import Any

from skills.shared import location, warning_list

KEYWORDS = {
    "payment": ["付款", "价款", "费用", "payment", "price"],
    "term": ["期限", "有效期", "履行期", "term", "deadline"],
    "liability": ["违约责任", "赔偿", "违约金", "liability", "damages"],
    "termination": ["解除", "终止", "termination"],
}
HEADING = re.compile(r"^(第?[一二三四五六七八九十\d]+[章节条、.．]|Article\s+\d+)", re.IGNORECASE)


def execute(payload: dict[str, Any]) -> dict[str, Any]:
    requested = set(payload.get("clause_types") or [])
    clauses: list[dict[str, Any]] = []
    for line_number, line in enumerate(payload["text"].splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        matches = [label for label, terms in KEYWORDS.items() if any(term.lower() in stripped.lower() for term in terms)]
        if requested:
            matches = [label for label in matches if label in requested]
        if matches or (not requested and HEADING.match(stripped)):
            clauses.append(
                {
                    "clause_type": matches[0] if matches else "other",
                    "text": stripped,
                    "line": line_number,
                    "confidence": 0.7 if matches else 0.45,
                    "source": location(line=line_number),
                    "document_id": payload.get("document_id"),
                }
            )
    return {
        "clauses": clauses,
        "warnings": warning_list() if clauses else ["no likely clause heading was detected"],
    }
