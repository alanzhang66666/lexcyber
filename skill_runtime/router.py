from typing import Any

from skill_runtime.registry import SkillRegistry
from skill_runtime.schemas import SkillManifest, SkillRequest

INTENT_RULES: list[tuple[tuple[str, ...], list[str]]] = [
    (("pdf",), ["document.parse.pdf", "document.page.anchor"]),
    (("docx", "word", "doc"), ["document.parse.docx", "document.page.anchor"]),
    (("ocr", "扫描", "扫描件"), ["document.ocr", "document.page.anchor"]),
    (("合同", "条款", "付款", "义务", "contract", "clause", "payment"), ["legal.document.classify", "legal.contract.clause.extract"]),
    (("判决", "起诉", "裁定", "文书类型", "classify"), ["legal.document.classify"]),
    (("原告", "被告", "当事人", "甲方", "乙方", "party", "plaintiff", "defendant"), ["legal.party.extract"]),
    (("事实", "金额", "日期", "fact", "amount"), ["legal.fact.extract"]),
    (("时间线", "timeline"), ["legal.timeline.build"]),
    (("法条", "引用", "citation", "《"), ["legal.citation.parse", "legal.citation.verify"]),
    (("检索", "法规", "司法解释", "search", "statute"), ["legal.source.search", "legal.source.authority.rank", "legal.source.effective_date.check"]),
    (("证据", "evidence"), ["legal.evidence.catalog", "legal.evidence.claim.support.map", "legal.evidence.contradiction.detect"]),
    (("脱敏", "隐私", "redact", "pii"), ["legal.document.redact"]),
    (("立案", "收案", "intake"), ["legal.case.intake.normalize", "legal.case.missing_information.detect"]),
    (("缺失", "补正", "missing"), ["legal.case.missing_information.detect"]),
    (("矛盾", "冲突", "consistency", "contradiction"), ["legal.review.factual_consistency", "legal.evidence.contradiction.detect"]),
]

DEFAULT_DOCUMENT_PIPELINE = [
    "legal.document.classify",
    "legal.party.extract",
    "legal.fact.extract",
    "legal.timeline.build",
    "legal.citation.parse",
    "legal.case.missing_information.detect",
]


class SkillRouter:
    def __init__(self, registry: SkillRegistry | None = None):
        self.registry = registry or SkillRegistry()

    def available(self) -> list[SkillManifest]:
        return self.registry.list()

    def select(self, query: str, context: dict[str, Any] | None = None) -> list[str]:
        context = context or {}
        text = f"{query}\n{context.get('source_text', '')}".lower()
        selected: list[str] = []
        for keywords, skill_ids in INTENT_RULES:
            if any(keyword.lower() in text for keyword in keywords):
                selected.extend(skill_ids)
        if not selected:
            selected = list(DEFAULT_DOCUMENT_PIPELINE)
        if context.get("document_bytes") or str(context.get("filename") or "").lower().endswith(".pdf"):
            selected = ["document.parse.pdf", "document.page.anchor", *selected]
        if str(context.get("filename") or "").lower().endswith(".docx"):
            selected = ["document.parse.docx", "document.page.anchor", *selected]
        selected.append("legal.review.factual_consistency")
        selected.append("legal.review.human_gate")
        available = {item.id for item in self.available()}
        deduped: list[str] = []
        for skill_id in selected:
            if skill_id in available and skill_id not in deduped:
                deduped.append(skill_id)
        return deduped

    def build_requests(self, query: str, context: dict[str, Any] | None = None, granted_permissions: list[str] | None = None) -> list[SkillRequest]:
        context = context or {}
        source_text = context.get("source_text") or query
        requests: list[SkillRequest] = []
        for index, skill_id in enumerate(self.select(query, context), start=1):
            manifest = self.registry.get(skill_id)
            payload = self._inputs_for(manifest, source_text, context)
            requests.append(
                SkillRequest(
                    skill_id=manifest.id,
                    skill_version=manifest.version,
                    input=payload,
                    metadata={"step_id": str(index), **context},
                    actor=str(context.get("actor", "agent")),
                    case_id=context.get("case_id"),
                    request_id=context.get("request_id"),
                    granted_permissions=granted_permissions,
                    human_approved=bool(context.get("human_approved")),
                )
            )
        return requests

    def _inputs_for(self, manifest: SkillManifest, source_text: str, context: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        properties = (manifest.input_schema or {}).get("properties", {})
        if "text" in properties:
            payload["text"] = source_text
        if "query" in properties:
            payload["query"] = context.get("query") or source_text[:500]
        if "document_id" in properties:
            payload["document_id"] = context.get("document_id") or (context.get("document_ids") or ["unknown"])[0]
        if "filename" in properties and context.get("filename"):
            payload["filename"] = context["filename"]
        if "content_base64" in properties and context.get("content_base64"):
            payload["content_base64"] = context["content_base64"]
        if "jurisdiction" in properties:
            payload["jurisdiction"] = context.get("jurisdiction") or "CN"
        if "as_of_date" in properties and context.get("as_of_date"):
            payload["as_of_date"] = context["as_of_date"]
        if "events" in properties and context.get("events"):
            payload["events"] = context["events"]
        if "items" in properties and context.get("evidence"):
            payload["items"] = context["evidence"]
        if "evidence" in properties and context.get("evidence"):
            payload["evidence"] = context["evidence"]
        if "facts" in properties and context.get("facts"):
            payload["facts"] = context["facts"]
        if "claims" in properties and context.get("claims"):
            payload["claims"] = context["claims"]
        if "parties" in properties and context.get("parties"):
            payload["parties"] = context["parties"]
        if "sources" in properties and context.get("legal_sources"):
            payload["sources"] = context["legal_sources"]
        if "fragments" in properties and context.get("fragments"):
            payload["fragments"] = context["fragments"]
        if "pages" in properties and context.get("pages"):
            payload["pages"] = context["pages"]
        if "intake" in properties:
            payload["intake"] = context.get("intake") or {"query": context.get("user_query") or source_text, "text": source_text}
        if "citation" in properties:
            payload["citation"] = context.get("citation") or source_text
        if "skill_results" in properties:
            payload["skill_results"] = context.get("skill_results") or []
        if "risk_level" in properties:
            payload["risk_level"] = context.get("risk_level") or "low"
        if "case" in properties:
            payload["case"] = context.get("case") or {"text": source_text}
        required = (manifest.input_schema or {}).get("required", [])
        for name in required:
            payload.setdefault(name, context.get(name) or ([] if name.endswith("s") else source_text))
        return payload
