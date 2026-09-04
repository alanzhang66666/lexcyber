import hashlib
import re
from datetime import datetime
from typing import Any


def document_classify(payload: dict[str, Any]) -> dict[str, Any]:
    text = f"{payload.get('filename', '')}\n{payload.get('text', '')}".lower()
    rules = [
        ("judgment", ["判决书", "裁定书", "判决", "裁定"]),
        ("complaint", ["起诉状", "诉状", "原告", "被告"]),
        ("contract", ["合同", "协议", "甲方", "乙方"]),
        ("evidence", ["证据", "取证", "鉴定意见", "聊天记录"]),
        ("regulation", ["条例", "办法", "规定", "法律条文"]),
    ]
    for label, keywords in rules:
        hits = sum(keyword.lower() in text for keyword in keywords)
        if hits:
            return {"label": label, "confidence": min(0.95, 0.55 + hits * 0.1), "matched_keywords": [k for k in keywords if k.lower() in text]}
    return {"label": "unknown", "confidence": 0.2, "matched_keywords": []}


def party_extract(payload: dict[str, Any]) -> dict[str, Any]:
    pattern = re.compile(r"(原告|被告|申请人|被申请人|上诉人|被上诉人|甲方|乙方)\s*[:：]?\s*([^\n，,；;。]{1,40})")
    parties = [{"role": role, "name": name.strip(" ：:、")} for role, name in pattern.findall(payload["text"])]
    return {"parties": parties, "warnings": [] if parties else ["no party label was detected"]}


def fact_extract(payload: dict[str, Any]) -> dict[str, Any]:
    text = payload["text"]
    facts: list[dict[str, Any]] = []
    date_pattern = re.compile(r"(?:\d{4}[年\-/]\d{1,2}[月\-/]\d{1,2}日?|\d{4}年\d{1,2}月\d{1,2}日)")
    amount_pattern = re.compile(r"(?:人民币|RMB|¥|￥)\s*[\d,]+(?:\.\d+)?\s*(?:元)?")
    for match in date_pattern.finditer(text):
        facts.append({"type": "date", "value": match.group(), "start": match.start(), "end": match.end()})
    for match in amount_pattern.finditer(text):
        facts.append({"type": "amount", "value": match.group(), "start": match.start(), "end": match.end()})
    warning = ["heuristic extraction; verify against the source document"] if facts else ["no supported fact pattern was detected"]
    return {"facts": facts, "warnings": warning}


def timeline_build(payload: dict[str, Any]) -> dict[str, Any]:
    events = list(payload.get("events", []))
    if not events and payload.get("text"):
        facts = fact_extract({"text": payload["text"]})["facts"]
        events = [{"date": fact["value"], "description": "date detected in source text", "source": {"start": fact["start"], "end": fact["end"]}} for fact in facts if fact["type"] == "date"]

    def sort_key(event: dict[str, Any]) -> tuple[int, str]:
        value = str(event.get("date", ""))
        normalized = re.sub(r"[年月]", "-", value).replace("日", "").replace("/", "-")
        try:
            return (0, datetime.strptime(normalized, "%Y-%m-%d").isoformat())
        except ValueError:
            return (1, value)

    return {"events": sorted(events, key=sort_key), "warnings": [] if events else ["no events supplied"]}


def citation_parse(payload: dict[str, Any]) -> dict[str, Any]:
    pattern = re.compile(r"《(?P<title>[^》]{1,100})》\s*第(?P<article>(?:\d+[之-]?\d*|[零〇一二三四五六七八九十百千万两]+))条(?:第(?P<paragraph>\d+)款)?(?:第(?P<item>[一二三四五六七八九十\d]+)项)?")
    citations = [{"title": match.group("title"), "article": match.group("article"), "paragraph": match.group("paragraph"), "item": match.group("item"), "raw": match.group(), "start": match.start(), "end": match.end()} for match in pattern.finditer(payload["text"])]
    return {"citations": citations, "warnings": [] if citations else ["no supported citation pattern was detected"]}


def source_search(payload: dict[str, Any]) -> dict[str, Any]:
    from retrieval.gateway import RetrievalGateway
    from retrieval.schemas import RetrievalQuery

    response = RetrievalGateway().search(RetrievalQuery(query=payload["query"], top_k=payload.get("top_k", 5), filters=payload.get("filters", {})))
    documents = [document.model_dump() for document in response.documents]
    return {"documents": documents, "warnings": [] if documents else ["no private knowledge-base result was returned"]}


def citation_verify(payload: dict[str, Any]) -> dict[str, Any]:
    search = source_search({"query": payload["citation"], "top_k": payload.get("top_k", 5)})
    matches = [document for document in search["documents"] if payload["citation"] in document.get("content", "") or payload["citation"] in str(document.get("metadata", {}))]
    status = "verified" if matches else "not_exactly_matched" if search["documents"] else "unavailable"
    return {"status": status, "matches": matches, "warnings": search["warnings"]}


def evidence_catalog(payload: dict[str, Any]) -> dict[str, Any]:
    items = payload.get("items", payload.get("evidence", []))
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        current = {"name": item} if isinstance(item, str) else dict(item)
        current.setdefault("evidence_id", f"E-{index:04d}")
        if current.get("content") and not current.get("sha256"):
            current["sha256"] = hashlib.sha256(str(current["content"]).encode("utf-8")).hexdigest()
        normalized.append(current)
    return {"items": normalized, "warnings": [] if normalized else ["no evidence items supplied"]}


def contract_clause_extract(payload: dict[str, Any]) -> dict[str, Any]:
    clauses: list[dict[str, Any]] = []
    keywords = {"payment": ["付款", "价款", "费用"], "term": ["期限", "有效期", "履行期"], "liability": ["违约责任", "赔偿", "违约金"], "termination": ["解除", "终止"]}
    for line_number, line in enumerate(payload["text"].splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        matches = [label for label, terms in keywords.items() if any(term in stripped for term in terms)]
        if matches or re.match(r"^(第?[一二三四五六七八九十\d]+[章节条、.．])", stripped):
            clauses.append({"clause_type": matches[0] if matches else "other", "text": stripped, "line": line_number})
    return {"clauses": clauses, "warnings": [] if clauses else ["no likely clause heading was detected"]}


def document_redact(payload: dict[str, Any]) -> dict[str, Any]:
    text = payload["text"]
    replacement = payload.get("replacement", "[REDACTED]")
    patterns = {"email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "phone": r"(?<!\d)1[3-9]\d{9}(?!\d)", "identity_number": r"(?<![0-9Xx])\d{17}[0-9Xx](?![0-9Xx])"}
    redactions: list[dict[str, Any]] = []
    redacted = text
    for kind, pattern in patterns.items():
        matches = list(re.finditer(pattern, redacted))
        redactions.extend({"type": kind, "value": match.group()} for match in matches)
        redacted = re.sub(pattern, replacement, redacted)
    warning = ["pattern-based redaction is not a complete privacy review"] if redactions else []
    return {"text": redacted, "redactions": redactions, "warnings": warning}
