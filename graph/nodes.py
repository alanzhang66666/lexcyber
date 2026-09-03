from graph.state import AgentState
from agents.reviewer.agent import ReviewerAgent
from agents.supervisor.agent import SupervisorAgent
from agents.tool_agent.agent import ToolAgent
from agents.worker.agent import WorkerAgent
from audit.logger import audit_event
from models.gateway import ModelGateway
from prompts.registry import PromptRegistry
from storage.postgres.repository import save_checkpoint, update_task_state
from tools.gateway import ToolGateway


model_gateway = ModelGateway()
prompt_registry = PromptRegistry()
worker_agent = WorkerAgent(model_gateway, prompt_registry)
supervisor_agent = SupervisorAgent()
tool_agent = ToolAgent(ToolGateway())
reviewer_agent = ReviewerAgent()


def _checkpoint(state: AgentState, node_name: str) -> None:
    task_id = state.get("task_id")
    if task_id:
        try:
            save_checkpoint(task_id, node_name, dict(state))
            update_task_state(task_id, dict(state))
        except Exception:
            pass


def input_normalize(state: AgentState) -> AgentState:
    state["user_query"] = " ".join(state.get("user_query", "").split())
    state.setdefault("messages", [])
    state.setdefault("retry_count", 0)
    _checkpoint(state, "input_normalize")
    return state


def supervisor(state: AgentState) -> AgentState:
    with audit_event(state, "supervisor", prompt_version="supervisor_v1:v1") as event:
        plan = supervisor_agent.plan(state.get("user_query", ""))
        state["task_plan"] = plan.steps
        state["current_task"] = plan.steps[0]
        event["model_output"] = {"steps": plan.steps}
    _checkpoint(state, "supervisor")
    return state


def worker(state: AgentState) -> AgentState:
    context = "\n".join(doc.get("content", "") for doc in state.get("retrieved_documents", []))
    with audit_event(state, "worker", prompt_version="worker_general_v1:v1") as event:
        result = worker_agent.run(state.get("user_query", ""), context)
        output = {"agent": "worker", "content": result.content, "model": result.model}
        state.setdefault("agent_outputs", []).append(output)
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
    with audit_event(state, "reviewer", prompt_version="reviewer_v1:v1") as event:
        status = reviewer_agent.review(state.get("user_query", ""), state.get("final_output", ""), state.get("retry_count", 0))
        state["review_status"] = status
        event["reviewer_result"] = status
        event["model_output"] = {"status": status}
    _checkpoint(state, "reviewer")
    return state


def output(state: AgentState) -> AgentState:
    _checkpoint(state, "output")
    return state
