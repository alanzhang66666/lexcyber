from langgraph.graph import END, START, StateGraph

from graph.nodes import (
    case_context_load,
    human_review,
    input_normalize,
    output,
    policy_gate,
    result_merge,
    reviewer,
    skill_executor_node,
    skill_router_node,
    supervisor,
)
from graph.routing import after_policy, after_reviewer, after_supervisor
from graph.state import AgentState


def build_workflow():
    graph = StateGraph(AgentState)
    graph.add_node("input_normalize", input_normalize)
    graph.add_node("case_context_load", case_context_load)
    graph.add_node("supervisor", supervisor)
    graph.add_node("skill_router", skill_router_node)
    graph.add_node("policy_gate", policy_gate)
    graph.add_node("skill_executor", skill_executor_node)
    graph.add_node("result_merge", result_merge)
    graph.add_node("reviewer", reviewer)
    graph.add_node("human_review", human_review)
    graph.add_node("output", output)
    graph.add_edge(START, "input_normalize")
    graph.add_edge("input_normalize", "case_context_load")
    graph.add_edge("case_context_load", "supervisor")
    graph.add_conditional_edges("supervisor", after_supervisor, {"skill_router": "skill_router"})
    graph.add_edge("skill_router", "policy_gate")
    graph.add_conditional_edges("policy_gate", after_policy, {"skill_executor": "skill_executor", "result_merge": "result_merge", "human_review": "human_review"})
    graph.add_edge("skill_executor", "result_merge")
    graph.add_edge("result_merge", "reviewer")
    graph.add_conditional_edges("reviewer", after_reviewer, {"supervisor": "supervisor", "human_review": "human_review", "output": "output"})
    graph.add_edge("human_review", "output")
    graph.add_edge("output", END)
    return graph.compile()
