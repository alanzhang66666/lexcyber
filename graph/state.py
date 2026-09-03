from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    task_id: str
    request_id: str
    session_id: str
    user_query: str
    messages: list[dict[str, str]]
    task_plan: list[str]
    current_task: str
    retrieved_documents: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    agent_outputs: list[dict[str, Any]]
    final_output: str
    review_status: str
    retry_count: int
    model_usage: dict[str, int]
    metadata: dict[str, Any]
