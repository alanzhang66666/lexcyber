from __future__ import annotations

import logging
import os
import socket
from typing import Any
from uuid import UUID

import httpx

from engine.contracts import ExecutionView
from engine.settings import settings
from engine.store import complete_execution, get_execution, mark_running, record_callback_failure
from engine.workflow import build_runner

logger = logging.getLogger(__name__)


def run_execution(payload: dict[str, Any]) -> dict[str, Any]:
    execution_id = UUID(str(payload["execution_id"]))
    owner = f"{socket.gethostname()}:{os.getpid()}"
    if not mark_running(execution_id, owner):
        return get_execution(execution_id) or {}
    try:
        result = build_runner().run(payload)
        waiting = bool(result.get("human_approval_required"))
        status = "waiting_review" if waiting else "completed"
        output = result.get("final_output")
        if output is None:
            output = result
        complete_execution(execution_id, status, "awaiting_review" if waiting else "output", output, None, None)
        _notify_application(execution_id)
        return result
    except TimeoutError as exc:
        complete_execution(execution_id, "timed_out", "timeout", None, "ENGINE_TIMEOUT", str(exc))
        _notify_application(execution_id)
        raise
    except Exception as exc:
        complete_execution(execution_id, "failed", "failed", None, "ENGINE_FAILED", str(exc), retryable=True)
        _notify_application(execution_id)
        raise


def _notify_application(execution_id: UUID) -> None:
    if not settings.app_callback_base_url:
        return
    view = get_execution(execution_id)
    if not view:
        return
    try:
        payload = ExecutionView.model_validate(view).model_dump(mode="json")
        with httpx.Client(timeout=10) as client:
            response = client.post(
                f"{settings.app_callback_base_url.rstrip('/')}/internal/v1/executions/{execution_id}/result",
                headers={"X-Service-Token": settings.service_token},
                json=payload,
            )
            response.raise_for_status()
    except Exception as failure:
        try:
            record_callback_failure(execution_id, str(failure))
        except Exception:
            logger.exception("unable to persist callback failure audit", extra={"execution_id": str(execution_id)})
        logger.exception("unable to deliver execution result callback", extra={"execution_id": str(execution_id)})
