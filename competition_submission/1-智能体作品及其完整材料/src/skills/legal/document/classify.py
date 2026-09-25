from typing import Any

from skills.shared import location, warning_list

RULES = [
    ("judgment", ["判决书", "裁定书", "判决", "裁定", "judgment", "ruling"]),
    ("complaint", ["起诉状", "诉状", "原告", "被告", "complaint", "petition"]),
    ("contract", ["合同", "协议", "甲方", "乙方", "contract", "agreement"]),
    ("evidence", ["证据", "取证", "鉴定意见", "聊天记录", "evidence", "exhibit"]),
    ("regulation", ["条例", "办法", "规定", "法律条文", "regulation", "statute"]),
]


def execute(payload: dict[str, Any]) -> dict[str, Any]:
    text = f"{payload.get('filename', '')}\n{payload.get('text', '')}"
    lowered = text.lower()
    best_label = "unknown"
    best_hits: list[str] = []
    best_score = 0
    for label, keywords in RULES:
        hits = [keyword for keyword in keywords if keyword.lower() in lowered]
        if len(hits) > best_score:
            best_label, best_hits, best_score = label, hits, len(hits)
    confidence = 0.2 if best_label == "unknown" else min(0.95, 0.55 + best_score * 0.1)
    return {
        "label": best_label,
        "confidence": confidence,
        "matched_keywords": best_hits,
        "document_id": payload.get("document_id"),
        "source": location(),
        "warnings": warning_list("heuristic classification; verify against the source document" if best_label != "unknown" else "no document type keyword was detected"),
    }
