import re
from typing import Any

from skills.shared import location, warning_list

PATTERN = re.compile(r"(原告|被告|申请人|被申请人|上诉人|被上诉人|甲方|乙方|Plaintiff|Defendant|Party A|Party B)\s*[:：]?\s*([^\n，,；;。]{1,80})", re.IGNORECASE)


def execute(payload: dict[str, Any]) -> dict[str, Any]:
    parties = []
    for match in PATTERN.finditer(payload["text"]):
        role, name = match.group(1), match.group(2).strip(" ：:、")
        parties.append(
            {
                "role": role,
                "name": name,
                "confidence": 0.8,
                "document_id": payload.get("document_id"),
                "source": location(start=match.start(), end=match.end()),
            }
        )
    return {"parties": parties, "warnings": warning_list() if parties else ["no party label was detected"]}
