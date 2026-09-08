from __future__ import annotations

import logging
import os
import socket
from typing import Any
from uuid import UUID

import httpx

from engine.adapters.sentencing import SentencingUnavailable
from engine.contracts import ExecutionView
from engine.document_parse import DocumentParseError
from engine.settings import settings
from engine.store import complete_execution, get_execution, mark_running, record_callback_failure
from engine.workflow import build_runner
from models.errors import ModelError, ModelTimeoutError

logger = logging.getLogger(__name__)


def _task_type(payload: dict[str, Any]) -> str | None:
    metadata = payload.get("metadata") or {}
    value = metadata.get("taskType")
    return str(value) if value else None


def _running_stage(task_type: str | None) -> str:
    if task_type == "document.parse":
        return "document_parsing"
    if task_type == "model.probe":
        return "model_probe"
    if task_type == "sentencing.calculate":
        return "sentencing"
    return "running"


def run_execution(payload: dict[str, Any]) -> dict[str, Any]:
    execution_id = UUID(str(payload["execution_id"]))
    owner = f"{socket.gethostname()}:{os.getpid()}"
    task_type = _task_type(payload)
    running_stage = _running_stage(task_type)
    if not mark_running(execution_id, owner, running_stage):
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
    except (TimeoutError, ModelTimeoutError) as exc:
        if task_type == "document.parse":
            code, stage = "DOCUMENT_PARSE_TIMEOUT", "document_parsing"
        elif task_type == "model.probe":
            code, stage = "MODEL_TIMEOUT", "model_probe"
        else:
            code, stage = "ENGINE_TIMEOUT", "timeout"
        complete_execution(execution_id, "timed_out", stage, None, code, str(exc))
        _notify_application(execution_id)
        raise
    except DocumentParseError as exc:
        complete_execution(execution_id, "failed", "document_parsing", None, exc.code, str(exc))
        _notify_application(execution_id)
        raise
    except SentencingUnavailable as exc:
        complete_execution(execution_id, "failed", "sentencing", None, exc.code, str(exc))
        _notify_application(execution_id)
        raise
    except ModelError as exc:
        complete_execution(execution_id, "failed", "model_probe", None, exc.code, str(exc))
        _notify_application(execution_id)
        raise
    except Exception as exc:
        if task_type == "document.parse":
            code, stage, retryable = "DOCUMENT_PARSE_FAILED", "document_parsing", False
        elif task_type == "model.probe":
            code, stage, retryable = "MODEL_FAILED", "model_probe", False
        else:
            code, stage, retryable = "ENGINE_FAILED", "failed", True
        complete_execution(execution_id, "failed", stage, None, code, str(exc), retryable=retryable)
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
