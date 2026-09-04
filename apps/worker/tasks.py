import dramatiq

from graph.state import AgentState
from graph.workflow import build_workflow
from storage.postgres.repository import complete_task, get_task, update_task_state
from storage.redis import configure_broker

configure_broker()


@dramatiq.actor(max_retries=2, time_limit=300_000)
def process_task(task_id: str) -> None:
    task = get_task(task_id)
    if not task:
        return
    state: AgentState = dict(task["state"])
    state["task_id"] = task_id
    update_task_state(task_id, state, status="running")
    try:
        result = build_workflow().invoke(state)
        complete_task(task_id, dict(result), status="completed")
    except Exception as exc:
        complete_task(task_id, state, status="failed", error=str(exc))
        raise
