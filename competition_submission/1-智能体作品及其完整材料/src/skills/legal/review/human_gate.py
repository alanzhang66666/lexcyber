from typing import Any

HIGH_RISK_HINTS = ("定罪", "罪名", "责任认定", "胜率", "诉讼时效", "上诉期限", "正式意见", "提交法院")


def execute(payload: dict[str, Any]) -> dict[str, Any]:
    risk_level = str(payload.get("risk_level") or "low")
    text = str(payload.get("text") or payload.get("query") or "")
    missing = list(payload.get("missing") or [])
    contradictions = list(payload.get("contradictions") or [])
    reasons = []
    if risk_level in {"high", "prohibited"}:
        reasons.append("risk_level requires a human gate")
    if any(hint in text for hint in HIGH_RISK_HINTS):
        reasons.append("query contains a high-risk legal action")
        risk_level = "high"
    if missing:
        reasons.append("required case information is missing")
    high_risk = risk_level in {"high", "prohibited"} or any(hint in text for hint in HIGH_RISK_HINTS)
    if high_risk:
        risk_level = "high"
        if "query contains a high-risk legal action" not in reasons and any(hint in text for hint in HIGH_RISK_HINTS):
            reasons.append("query contains a high-risk legal action")
    if contradictions:
        reasons.append("conflicts must be reviewed by a human")
    need_human = high_risk or bool(contradictions)
    return {
        "need_human": need_human,
        "risk_level": "high" if high_risk else risk_level,
        "reasons": reasons if need_human else [],
        "warnings": reasons,
    }
