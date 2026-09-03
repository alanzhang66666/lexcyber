from langgraph.graph import END, START, StateGraph

from graph.nodes import input_normalize, output, reviewer, supervisor, tool, worker
from graph.routing import after_reviewer, after_supervisor
from graph.state import AgentState


def build_workflow():
    graph = StateGraph(AgentState)
    graph.add_node("input_normalize", input_normalize)
    graph.add_node("supervisor", supervisor)
    graph.add_node("worker", worker)
    graph.add_node("tool", tool)
    graph.add_node("reviewer", reviewer)
    graph.add_node("output", output)
    graph.add_edge(START, "input_normalize")
    graph.add_edge("input_normalize", "supervisor")
    graph.add_conditional_edges("supervisor", after_supervisor, {"worker": "worker", "tool": "tool"})
    graph.add_edge("worker", "tool")
    graph.add_edge("tool", "reviewer")
    graph.add_conditional_edges("reviewer", after_reviewer, {"supervisor": "supervisor", "output": "output"})
    graph.add_edge("output", END)
    return graph.compile()
