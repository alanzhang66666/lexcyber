from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    task_id: str
    request_id: str
    session_id: str
    user_query: str
    messages: list[dict[str, str]]
    task_plan: list[dict[str, Any]]
    current_task: str
    retrieved_documents: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    agent_outputs: list[dict[str, Any]]
    final_output: dict[str, Any] | str
    review_status: str
    review_result: dict[str, Any]
    retry_count: int
    model_usage: dict[str, int]
    metadata: dict[str, Any]
    available_skills: list[dict[str, Any]]
    selected_skills: list[str]
    skill_requests: list[dict[str, Any]]
    skill_results: list[dict[str, Any]]
    skill_errors: list[dict[str, Any]]
    skill_usage: list[dict[str, Any]]
    case_id: str | None
    jurisdiction: str | None
    as_of_date: str | None
    document_ids: list[str]
    source_text: str
    facts: list[dict[str, Any]]
    parties: list[dict[str, Any]]
    timeline: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    legal_sources: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    risk_level: str
    human_approval_required: bool
    human_review_id: str | None
    audit_events: list[dict[str, Any]]
