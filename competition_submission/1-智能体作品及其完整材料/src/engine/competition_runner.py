from __future__ import annotations

import json
import re
from threading import BoundedSemaphore
from typing import Any

from audit.logger import audit_event
from config.settings import settings
from engine.competition_knowledge import search_knowledge
from engine.document_parse import DocumentParseRunner
from models.errors import ModelError, ModelFailedError, ModelNotConfiguredError
from models.gateway import ModelGateway
from models.schemas import ModelRequest
from skills.legal.case.fact_extract import execute as extract_facts
from skills.legal.case.party_extract import execute as extract_parties
from skills.legal.case.timeline_build import execute as build_timeline
from skills.legal.review.factual_consistency import execute as check_consistency

_MODEL_SEMAPHORE = BoundedSemaphore(max(1, settings.model_max_concurrency))


class CompetitionAnalysisRunner:
    """A bounded, source-grounded and human-gated competition workflow."""

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        task_state = {
            "request_id": str(payload.get("request_id", "unknown")),
            "task_id": str(payload.get("task_id", "unknown")),
            "execution_id": str(payload.get("execution_id", "unknown")),
            "user_query": payload.get("query", ""),
            "engine_mode": True,
        }
        metadata = payload.get("metadata") or {}
        with audit_event(task_state, "competition.document_parse", stage="document_parse") as event:
            parsed = DocumentParseRunner().run(payload)
            event["tool_calls"] = ["document.parse"]
            event["document_id"] = parsed.get("documentId")

        source_text = str(parsed.get("text") or "")
        if not source_text.strip():
            raise ModelFailedError("parsed document has no text", code="DOCUMENT_PARSE_EMPTY")
        bounded_text = source_text[:60_000]
        extraction_context = {"text": bounded_text, "document_id": parsed.get("documentId")}
        with audit_event(task_state, "competition.extraction", stage="structured_extraction") as event:
            parties = extract_parties(extraction_context)
            facts = extract_facts(extraction_context)
            timeline = build_timeline(extraction_context)
            consistency = check_consistency({"facts": facts.get("facts", [])})
            event["tool_calls"] = [
                "legal.party.extract",
                "legal.fact.extract",
                "legal.timeline.build",
                "legal.review.factual_consistency",
            ]
            event["model_output"] = {
                "parties": len(parties.get("parties", [])),
                "facts": len(facts.get("facts", [])),
                "events": len(timeline.get("events", [])),
                "conflicts": len(consistency.get("issues", [])),
            }

        query = str(payload.get("query") or "")
        retrieval_query = f"{query}\n{bounded_text[:2500]}"
        with audit_event(task_state, "competition.retrieval", stage="knowledge_retrieval") as event:
            retrieval = search_knowledge(
                retrieval_query,
                as_of_date=metadata.get("as_of_date"),
                top_k=5,
            )
            event["tool_calls"] = ["knowledge.search"]
            event["knowledge_refs"] = [item.get("id") for item in retrieval.get("documents", [])]

        if not retrieval.get("documents"):
            return self._blocked_result(parsed, parties, facts, timeline, retrieval, consistency, "KNOWLEDGE_NOT_FOUND")

        with audit_event(task_state, "competition.model_analysis", stage="grounded_model_analysis") as event:
            analysis, model_stats = self._invoke_structured(
                query=query,
                source_text=bounded_text,
                parsed=parsed,
                parties=parties,
                facts=facts,
                timeline=timeline,
                retrieval=retrieval,
            )
            event["model_name"] = model_stats.get("model")
            event["token_usage"] = model_stats.get("tokenUsage", {})
            event["model_output"] = {"schemaVersion": analysis.get("schemaVersion")}

        blockers = list(retrieval.get("warnings") or []) if not retrieval.get("documents") else []
        blockers.extend(item.get("message", str(item)) for item in consistency.get("issues", []))
        invalid_sources = self._invalid_source_refs(analysis, retrieval)
        if invalid_sources:
            blockers.append(f"model cited sources outside retrieved set: {', '.join(invalid_sources)}")
        if not self._has_source_refs(analysis):
            blockers.append("MODEL_MISSING_SOURCE_REFS")
        if not str(analysis.get("summary") or "").strip():
            blockers.append("MODEL_MISSING_SUMMARY")
        if any(item.get("effective_status") != "effective" for item in retrieval.get("documents", [])):
            blockers.append("法源生效状态需要人工确认")

        status = "blocked" if blockers else "ready_for_review"
        return {
            "schemaVersion": "case.assist.v1",
            "taskType": "case.assist.analyze",
            "status": status,
            "humanApprovalRequired": True,
            "human_approval_required": True,
            "document": parsed,
            "extraction": {"parties": parties.get("parties", []), "facts": facts.get("facts", []), "timeline": timeline.get("events", [])},
            "retrieval": retrieval,
            "analysis": analysis,
            "verification": {
                "status": "blocked" if blockers else "passed_with_human_gate",
                "blockers": blockers,
                "consistency": consistency,
            },
            "model": model_stats,
            "warnings": list(parsed.get("warnings") or []) + list(facts.get("warnings") or []),
            "blockers": blockers,
        }

    def _invoke_structured(self, *, query: str, source_text: str, parsed: dict[str, Any], parties: dict[str, Any], facts: dict[str, Any], timeline: dict[str, Any], retrieval: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        gateway = ModelGateway()
        if gateway.settings.model_provider == "stub" and not settings.allow_stub_model:
            raise ModelNotConfiguredError("competition workflow refuses stub model; configure the model API in user settings")
        prompt = "\n\n".join(
            (
                self._prompt("system_guardrails_v1.md"),
                self._prompt("verification_v1.md"),
            )
        )
        task_prompt = self._prompt("grounded_analysis_v1.md")
        context = {
            "query": query,
            "document": {"id": parsed.get("documentId"), "format": parsed.get("format")},
            "text": source_text,
            "parties": parties.get("parties", []),
            "facts": facts.get("facts", []),
            "timeline": timeline.get("events", []),
            "retrieved_sources": retrieval.get("documents", []),
            "required_output": {
                "schemaVersion": "case.assist.analysis.v1",
                "summary": "string",
                "candidate_paths": "array",
                "risks": "array",
                "missing_information": "array",
                "source_refs": "array of retrieved source ids",
                "document_refs": "array of document locators",
            },
        }
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"{task_prompt}\n\n输入 JSON：{json.dumps(context, ensure_ascii=False)}"},
        ]
        attempts = 0
        total_usage: dict[str, int] = {}
        last_error: Exception | None = None
        last_response = None
        for attempts in range(1, settings.model_max_retries + 2):
            if attempts > settings.model_max_calls_per_task:
                break
            try:
                with _MODEL_SEMAPHORE:
                    response = gateway.invoke(
                        ModelRequest(task_type="case.assist.analyze", messages=messages),
                        fallback=False,
                    )
                last_response = response
                for key, value in response.token_usage.items():
                    total_usage[key] = total_usage.get(key, 0) + int(value)
                parsed_json = self._parse_json(response.content)
                if not isinstance(parsed_json, dict):
                    raise ValueError("model output must be a JSON object")
                stats = {
                    "provider": response.provider,
                    "model": response.model,
                    "latencyMs": response.latency_ms,
                    "tokenUsage": total_usage,
                    "attempts": attempts,
                    "promptVersion": "system_guardrails_v1+grounded_analysis_v1+verification_v1",
                }
                return parsed_json, stats
            except Exception as exc:
                last_error = exc
                messages.append({"role": "user", "content": "上一次输出未通过 JSON 结构校验。只返回符合 required_output 的 JSON，不要 Markdown。"})
        if last_response is not None and last_error:
            raise ModelFailedError(f"model structured output invalid after {attempts} attempts: {last_error}", code="MODEL_INVALID_STRUCTURED_OUTPUT")
        if isinstance(last_error, ModelError):
            raise last_error
        raise ModelFailedError(f"model invocation failed: {last_error}") from last_error

    def _blocked_result(self, parsed: dict[str, Any], parties: dict[str, Any], facts: dict[str, Any], timeline: dict[str, Any], retrieval: dict[str, Any], consistency: dict[str, Any], code: str) -> dict[str, Any]:
        return {
            "schemaVersion": "case.assist.v1",
            "taskType": "case.assist.analyze",
            "status": "blocked",
            "humanApprovalRequired": True,
            "human_approval_required": True,
            "document": parsed,
            "extraction": {"parties": parties.get("parties", []), "facts": facts.get("facts", []), "timeline": timeline.get("events", [])},
            "retrieval": retrieval,
            "analysis": {"schemaVersion": "case.assist.analysis.v1", "summary": "未形成可复核的辅助分析", "candidate_paths": [], "risks": [], "missing_information": [code]},
            "verification": {"status": "blocked", "blockers": [code], "consistency": consistency},
            "model": {"provider": settings.model_provider, "model": settings.model_name, "attempts": 0, "tokenUsage": {}},
            "blockers": [code],
        }

    def _invalid_source_refs(self, analysis: dict[str, Any], retrieval: dict[str, Any]) -> list[str]:
        allowed = {str(item.get("id")) for item in retrieval.get("documents", [])}
        refs = list(analysis.get("source_refs") or [])
        for item in analysis.get("candidate_paths") or []:
            refs.extend(item.get("source_refs") or item.get("legal_source_ids") or [])
        return sorted({str(item) for item in refs if str(item) not in allowed})

    @staticmethod
    def _has_source_refs(analysis: dict[str, Any]) -> bool:
        if analysis.get("source_refs"):
            return True
        return any(item.get("source_refs") or item.get("legal_source_ids") for item in analysis.get("candidate_paths") or [])

    def _prompt(self, filename: str) -> str:
        from pathlib import Path
        root = Path(settings.prompt_root)
        path = root / filename
        if path.exists():
            return path.read_text(encoding="utf-8")
        return "仅基于输入材料生成结构化、可复核的辅助分析，不得作出司法结论。"

    @staticmethod
    def _parse_json(value: str) -> Any:
        text = str(value or "").strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.DOTALL).strip()
        return json.loads(text)
