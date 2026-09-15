import re
from decimal import Decimal
from typing import Any

from skills.shared import location

DATE_PATTERN = re.compile(r"(?:\d{4}年\d{1,2}月(?:\d{1,2}日)?|\d{4}[\-/]\d{1,2}(?:[\-/]\d{1,2})?)")
AMOUNT_PATTERN = re.compile(
    r"(?:(?P<currency>人民币|RMB|CNY|USD|\$|¥|￥)\s*)?(?P<number>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>亿元|万元|万余元|元|dollars?)",
    re.IGNORECASE,
)

AMOUNT_KIND_HINTS = (
    (("账户总", "总流水", "总流入"), "account_total_flow"),
    (("涉诈", "诈骗金额", "诈骗损失"), "fraud_related_inflow"),
    (("支付结算",), "payment_settlement"),
    (("犯罪数额",), "crime_amount"),
    (("犯罪所得", "违法所得"), "crime_proceeds"),
    (("个人参与",), "personal_participation"),
    (("个人获利", "非法获利", "提成", "报酬"), "personal_profit"),
    (("退赔", "退缴", "退赃"), "restitution"),
)


def _amount_kind(context: str) -> str:
    best_position = -1
    best_kind = "unclassified_amount"
    for hints, kind in AMOUNT_KIND_HINTS:
        position = max((context.rfind(hint) for hint in hints), default=-1)
        if position > best_position:
            best_position = position
            best_kind = kind
    return best_kind


def _normalized_amount(match: re.Match[str]) -> tuple[float, str]:
    number = Decimal(match.group("number").replace(",", ""))
    unit = match.group("unit").lower()
    if unit in {"万元", "万余元"}:
        number *= Decimal("10000")
    elif unit == "亿元":
        number *= Decimal("100000000")
    currency_token = (match.group("currency") or "").upper()
    currency = "USD" if currency_token in {"USD", "$"} or "DOLLAR" in unit.upper() else "CNY"
    return float(number), currency


def execute(payload: dict[str, Any]) -> dict[str, Any]:
    text = payload["text"]
    facts: list[dict[str, Any]] = []
    for match in DATE_PATTERN.finditer(text):
        facts.append(
            {
                "type": "date",
                "value": match.group(),
                "confidence": 0.75,
                "extraction_method": "regex",
                "verification_status": "candidate",
                "document_id": payload.get("document_id"),
                "source": location(start=match.start(), end=match.end()),
            }
        )
    for match in AMOUNT_PATTERN.finditer(text):
        normalized_value, currency = _normalized_amount(match)
        context = text[max(0, match.start() - 24) : match.start()]
        facts.append(
            {
                "type": "amount",
                "value": match.group(),
                "amount_kind": _amount_kind(context),
                "normalized_value": normalized_value,
                "currency": currency,
                "confidence": 0.75,
                "extraction_method": "regex_with_context_hint",
                "verification_status": "candidate",
                "document_id": payload.get("document_id"),
                "source": location(start=match.start(), end=match.end()),
            }
        )
    warning = "heuristic extraction only; amount kind, negation, actor attribution, stage, and conflicts require confirmation"
    return {"facts": facts, "warnings": [warning] if facts else ["no supported fact pattern was detected"]}
