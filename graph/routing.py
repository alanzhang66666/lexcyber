from graph.state import AgentState


def after_supervisor(state: AgentState) -> str:
    return state.get("current_task", "worker")


def after_reviewer(state: AgentState) -> str:
    status = state.get("review_status", "NEED_HUMAN")
    if status == "RETRY" and state.get("retry_count", 0) < 2:
        state["retry_count"] = state.get("retry_count", 0) + 1
        return "supervisor"
    return "output"
