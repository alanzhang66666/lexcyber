from agents.reviewer.agent import ReviewerAgent
from agents.supervisor.agent import SupervisorAgent
from agents.tool_agent.agent import ToolAgent
from agents.worker.agent import WorkerAgent
from audit.logger import audit_event
from graph.state import AgentState
from models.gateway import ModelGateway
from prompts.registry import PromptRegistry
from skill_runtime.audit import InMemoryAuditSink
from skill_runtime.errors import SkillNeedHumanError, SkillRuntimeError
from skill_runtime.executor import SkillExecutor
from skill_runtime.policy import DEFAULT_AGENT_PERMISSIONS, evaluate
from skill_runtime.registry import SkillRegistry
from skill_runtime.router import SkillRouter
from skill_runtime.schemas import SkillRequest
from storage.postgres.repository import save_checkpoint, update_task_state
from tools.gateway import ToolGateway

model_gateway = ModelGateway()
prompt_registry = PromptRegistry()
worker_agent = WorkerAgent(model_gateway, prompt_registry)
skill_registry = SkillRegistry()
skill_router = SkillRouter(skill_registry)
supervisor_agent = SupervisorAgent(skill_router)
tool_agent = ToolAgent(ToolGateway())
reviewer_agent = ReviewerAgent()
skill_executor_runtime = SkillExecutor(skill_registry, audit_sink=InMemoryAuditSink())


def _checkpoint(state: AgentState, node_name: str) -> None:
    task_id = state.get("task_id")
    if task_id:
        try:
            save_checkpoint(task_id, node_name, dict(state))
            update_task_state(task_id, dict(state))
        except Exception:
            pass


def _context(state: AgentState) -> dict:
    metadata = dict(state.get("metadata") or {})
    return {
        "source_text": state.get("source_text") or metadata.get("text") or state.get("user_query", ""),
        "user_query": state.get("user_query", ""),
        "query": state.get("user_query", ""),
        "case_id": state.get("case_id") or metadata.get("case_id"),
        "request_id": state.get("request_id"),
        "jurisdiction": state.get("jurisdiction") or metadata.get("jurisdiction") or "CN",
        "as_of_date": state.get("as_of_date") or metadata.get("as_of_date"),
        "document_id": (state.get("document_ids") or metadata.get("document_ids") or ["unknown"])[0],
        "document_ids": state.get("document_ids") or metadata.get("document_ids") or [],
        "filename": metadata.get("filename"),
        "content_base64": metadata.get("content_base64"),
        "pages": metadata.get("pages"),
        "facts": state.get("facts") or [],
        "parties": state.get("parties") or [],
        "evidence": state.get("evidence") or metadata.get("evidence") or [],
        "claims": metadata.get("claims") or [],
        "legal_sources": state.get("legal_sources") or state.get("retrieved_documents") or [],
        "events": state.get("timeline") or [],
        "skill_results": state.get("skill_results") or [],
        "risk_level": state.get("risk_level") or "low",
        "missing": (state.get("metadata") or {}).get("missing") or [],
        "contradictions": metadata.get("contradictions") or [],
        "actor": "agent",
        "granted_permissions": DEFAULT_AGENT_PERMISSIONS,
        "human_approved": bool(metadata.get("human_approved")),
        "citation": metadata.get("citation") or state.get("user_query", ""),
        "intake": metadata.get("intake"),
        "case": metadata.get("case"),
    }


def _absorb(state: AgentState, result: dict) -> None:
    output = result.get("output") or {}
    if output.get("parties"):
        state["parties"] = output["parties"]
    if output.get("facts"):
        state["facts"] = output["facts"]
    if output.get("events"):
        state["timeline"] = output["events"]
    if output.get("items"):
        state["evidence"] = output["items"]
    if output.get("citations"):
        state.setdefault("citations", []).extend(output["citations"])
    if output.get("documents"):
        state["legal_sources"] = output["documents"]
        state["retrieved_documents"] = output["documents"]
    if output.get("sources"):
        state["legal_sources"] = output["sources"]
    if output.get("pages"):
        state.setdefault("metadata", {})
        state["metadata"]["pages"] = output["pages"]
    if result.get("skill_id", "").startswith("document.parse") and output.get("text"):
        state["source_text"] = output["text"]
    if output.get("need_human") or result.get("status") == "need_human":
        state["human_approval_required"] = True
    if output.get("missing"):
        state.setdefault("metadata", {})
        state["metadata"]["missing"] = output["missing"]
    if output.get("has_conflict"):
        state.setdefault("metadata", {})
        state["metadata"]["contradictions"] = output.get("contradictions", [])


def input_normalize(state: AgentState) -> AgentState:
    state["user_query"] = " ".join(state.get("user_query", "").split())
    state.setdefault("messages", [])
    state.setdefault("retry_count", 0)
    state.setdefault("skill_results", [])
    state.setdefault("skill_errors", [])
    state.setdefault("metadata", {})
    _checkpoint(state, "input_normalize")
    return state


def case_context_load(state: AgentState) -> AgentState:
    metadata = state.get("metadata") or {}
    state.setdefault("case_id", metadata.get("case_id"))
    state.setdefault("jurisdiction", metadata.get("jurisdiction") or "CN")
    state.setdefault("as_of_date", metadata.get("as_of_date"))
    state.setdefault("document_ids", metadata.get("document_ids") or [])
    state["source_text"] = metadata.get("text") or state.get("source_text") or state.get("user_query", "")
    state["available_skills"] = skill_executor_runtime.list_skills()
    if state.get("case_id"):
        try:
            from domain.cases.repository import load_matter

            matter = load_matter(str(state["case_id"]))
            if matter:
                state["jurisdiction"] = state.get("jurisdiction") or matter.get("jurisdiction")
                state.setdefault("parties", matter.get("parties") or [])
        except Exception:
            pass
    _checkpoint(state, "case_context_load")
    return state


def supervisor(state: AgentState) -> AgentState:
    with audit_event(state, "supervisor", prompt_version="supervisor_v1:v1") as event:
        plan = supervisor_agent.plan(state.get("user_query", ""), _context(state))
        state["task_plan"] = plan.steps
        state["current_task"] = "skill_router"
        state["risk_level"] = plan.risk_level
        if plan.requires_human_review:
            state["human_approval_required"] = True
        event["model_output"] = {"goal": plan.goal, "steps": [step["skill_id"] for step in plan.steps], "risk_level": plan.risk_level}
    _checkpoint(state, "supervisor")
    return state


def skill_router_node(state: AgentState) -> AgentState:
    context = _context(state)
    requests = skill_router.build_requests(state.get("user_query", ""), context, granted_permissions=DEFAULT_AGENT_PERMISSIONS)
    if state.get("task_plan"):
        selected = [step["skill_id"] for step in state["task_plan"] if isinstance(step, dict)]
        if selected:
            requests = [item for item in requests if item.skill_id in selected] or requests
    state["selected_skills"] = [item.skill_id for item in requests]
    state["skill_requests"] = [item.model_dump() for item in requests]
    _checkpoint(state, "skill_router")
    return state


def policy_gate(state: AgentState) -> AgentState:
    allowed: list[dict] = []
    for raw in state.get("skill_requests", []):
        request = SkillRequest.model_validate(raw)
        try:
            manifest = skill_registry.get(request.skill_id, request.skill_version)
            decision = evaluate(manifest, request)
            raw["permission_result"] = decision.permission_result
            if decision.human_approval_required:
                state["human_approval_required"] = True
            allowed.append(raw)
        except SkillNeedHumanError as exc:
            state["human_approval_required"] = True
            state.setdefault("skill_errors", []).append({"skill_id": request.skill_id, "error": str(exc), "status": "need_human"})
        except SkillRuntimeError as exc:
            state.setdefault("skill_errors", []).append({"skill_id": request.skill_id, "error": str(exc), "status": getattr(exc, "status", "denied")})
    state["skill_requests"] = allowed
    _checkpoint(state, "policy_gate")
    return state


def skill_executor_node(state: AgentState) -> AgentState:
    results = list(state.get("skill_results") or [])
    usage = list(state.get("skill_usage") or [])
    with audit_event(state, "skill_executor", prompt_version="skill_runtime:v0.2") as event:
        for raw in state.get("skill_requests", []):
            request = SkillRequest.model_validate(raw)
            manifest = skill_registry.get(request.skill_id, request.skill_version)
            request.input = skill_router._inputs_for(manifest, _context(state).get("source_text", ""), _context(state))
            result = skill_executor_runtime.execute(request)
            dumped = result.model_dump()
            results.append(dumped)
            usage.append({"skill_id": result.skill_id, "status": result.status, "duration_ms": result.duration_ms})
            _absorb(state, dumped)
            if result.status in {"failed", "timeout", "denied"}:
                state.setdefault("skill_errors", []).append(dumped)
            if result.status == "need_human":
                state["human_approval_required"] = True
                break
        event["tool_calls"] = state.get("selected_skills", [])
        event["model_output"] = {"executed": len(results)}
    state["skill_results"] = results
    state["skill_usage"] = usage
    _checkpoint(state, "skill_executor")
    return state


def result_merge(state: AgentState) -> AgentState:
    completed = [item for item in state.get("skill_results", []) if item.get("status") == "completed"]
    state["final_output"] = {
        "summary": state.get("user_query"),
        "selected_skills": state.get("selected_skills", []),
        "parties": state.get("parties", []),
        "facts": state.get("facts", []),
        "timeline": state.get("timeline", []),
        "citations": state.get("citations", []),
        "evidence": state.get("evidence", []),
        "legal_sources": state.get("legal_sources", []),
        "skill_results": completed,
        "warnings": [warning for item in completed for warning in item.get("warnings", [])],
    }
    _checkpoint(state, "result_merge")
    return state


def worker(state: AgentState) -> AgentState:
    context = "\n".join(doc.get("content", "") for doc in state.get("retrieved_documents", []))
    with audit_event(state, "worker", prompt_version="worker_general_v1:v1") as event:
        result = worker_agent.run(state.get("user_query", ""), context)
        output = {"agent": "worker", "content": result.content, "model": result.model}
        state.setdefault("agent_outputs", []).append(output)
        final_output = state.get("final_output")
        if isinstance(final_output, dict):
            final_output["model_summary"] = result.content
        else:
            state["final_output"] = result.content
        state["model_usage"] = result.token_usage
        event["model_name"] = result.model
        event["model_output"] = output
        event["token_usage"] = result.token_usage
    _checkpoint(state, "worker")
    return state


def tool(state: AgentState) -> AgentState:
    with audit_event(state, "tool_agent", prompt_version="retrieval_query_v1:v1") as event:
        result = tool_agent.retrieve(state.get("user_query", ""))
        documents = [doc.model_dump() for doc in result.documents]
        state["retrieved_documents"] = documents
        state.setdefault("tool_results", []).append({"tool": "retrieval.search", "documents": documents})
        event["tool_calls"] = ["retrieval.search"]
        event["model_output"] = {"documents": len(documents)}
    _checkpoint(state, "tool")
    return state


def reviewer(state: AgentState) -> AgentState:
    final_output = state.get("final_output") or ""
    candidate = final_output if isinstance(final_output, str) else str(final_output.get("summary") or final_output)
    with audit_event(state, "reviewer", prompt_version="reviewer_v1:v1") as event:
        review = reviewer_agent.review_detailed(state.get("user_query", ""), candidate, state.get("retry_count", 0), dict(state))
        state["review_status"] = review.status
        state["review_result"] = review.model_dump()
        event["reviewer_result"] = review.status
        event["model_output"] = review.model_dump()
    _checkpoint(state, "reviewer")
    return state


def human_review(state: AgentState) -> AgentState:
    payload = {"skill_results": state.get("skill_results", []), "query": state.get("user_query"), "review_result": state.get("review_result")}
    try:
        from domain.reviews.repository import enqueue_review

        review = enqueue_review(state.get("case_id"), state.get("task_id"), state.get("risk_level"), "workflow requested human review", payload)
        state["human_review_id"] = review["id"]
    except Exception:
        from uuid import uuid4

        state["human_review_id"] = str(uuid4())
    state["review_status"] = "NEED_HUMAN"
    state["human_approval_required"] = True
    state["final_output"] = {"status": "NEED_HUMAN", "review_id": state["human_review_id"], "skill_results": state.get("skill_results", [])}
    _checkpoint(state, "human_review")
    return state


def output(state: AgentState) -> AgentState:
    _checkpoint(state, "output")
    return state
