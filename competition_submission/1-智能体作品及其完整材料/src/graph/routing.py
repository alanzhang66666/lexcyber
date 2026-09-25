from graph.state import AgentState


def after_supervisor(state: AgentState) -> str:
    return "skill_router"


def after_policy(state: AgentState) -> str:
    if state.get("human_approval_required") and not state.get("skill_requests"):
        return "human_review"
    if not state.get("skill_requests"):
        return "result_merge"
    return "skill_executor"


def after_reviewer(state: AgentState) -> str:
    status = state.get("review_status", "NEED_HUMAN")
    if status == "RETRY" and state.get("retry_count", 0) < 2:
        state["retry_count"] = state.get("retry_count", 0) + 1
        return "supervisor"
    if status == "NEED_HUMAN":
        return "human_review"
    return "output"
