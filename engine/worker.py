from __future__ import annotations

import os
import socket
from typing import Any
from uuid import UUID

from engine.store import complete_execution, mark_running
from graph.workflow import build_workflow


def run_execution(payload: dict[str, Any]) -> dict[str, Any]:
    execution_id = UUID(str(payload["execution_id"]))
    owner = f"{socket.gethostname()}:{os.getpid()}"
    mark_running(execution_id, owner)
    state = {
        "request_id": str(payload["request_id"]),
        "user_query": payload["query"],
        "metadata": payload.get("metadata") or {},
        "execution_id": str(execution_id),
        "engine_mode": True,
    }
    try:
        result = dict(build_workflow().invoke(state))
        waiting = bool(result.get("human_approval_required"))
        status = "waiting_review" if waiting else "completed"
        complete_execution(execution_id, status, "awaiting_review" if waiting else "output", result.get("final_output"), None, None)
        return result
    except TimeoutError as exc:
        complete_execution(execution_id, "timed_out", "timeout", None, "ENGINE_TIMEOUT", str(exc))
        raise
    except Exception as exc:
        complete_execution(execution_id, "failed", "failed", None, "ENGINE_FAILED", str(exc))
        raise
