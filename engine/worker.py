from __future__ import annotations

import json
import logging
import os
import socket
from typing import Any
from uuid import UUID

import httpx

from engine.adapters.module_analysis import ModuleAnalysisError
from engine.adapters.sentencing import SentencingInputError, SentencingUnavailable
from engine.contracts import ExecutionView
from engine.document_parse import DocumentParseError
from engine.rules.evaluator import AmountAggregationError
from engine.rules.registry import RegistryError
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
    if task_type == "compliance.analyze":
        return "compliance"
    if task_type == "conviction.analyze":
        return "conviction"
    if task_type == "draft.render":
        return "draft_render"
    return "running"


def run_execution(payload: dict[str, Any]) -> dict[str, Any]:
    execution_id = UUID(str(payload["execution_id"]))
    owner = f"{socket.gethostname()}:{os.getpid()}"
    task_type = _task_type(payload)
    running_stage = _running_stage(task_type)
    fencing_token = mark_running(execution_id, owner, running_stage)
    if fencing_token is None:
        return get_execution(execution_id) or {}
    try:
        result = build_runner().run(payload)
        waiting = bool(result.get("human_approval_required"))
        output = result.get("final_output")
        if output is None:
            output = result
        applied = complete_execution(
            execution_id, "completed", "awaiting_review" if waiting else "output", fencing_token,
            output, None, None, owner=owner, human_review_required=waiting)
        if applied:
            _notify_application(execution_id)
        return result
    except SentencingInputError as exc:
        error = exc.as_dict()
        if complete_execution(
            execution_id, "failed", "sentencing", fencing_token, None, exc.code,
            json.dumps(error, ensure_ascii=False, sort_keys=True), retryable=False, owner=owner,
        ):
            _notify_application(execution_id)
        raise
    except (TimeoutError, ModelTimeoutError) as exc:
        if task_type == "document.parse":
            code, stage = "DOCUMENT_PARSE_TIMEOUT", "document_parsing"
        elif task_type == "model.probe":
            code, stage = "MODEL_TIMEOUT", "model_probe"
        else:
            code, stage = "ENGINE_TIMEOUT", "timeout"
        if complete_execution(execution_id, "failed", stage, fencing_token, None, code, str(exc), owner=owner):
            _notify_application(execution_id)
        raise
    except DocumentParseError as exc:
        if complete_execution(execution_id, "failed", "document_parsing", fencing_token, None, exc.code, str(exc), owner=owner):
            _notify_application(execution_id)
        raise
    except SentencingUnavailable as exc:
        if complete_execution(execution_id, "failed", "sentencing", fencing_token, None, exc.code, str(exc), owner=owner):
            _notify_application(execution_id)
        raise
    except ModuleAnalysisError as exc:
        stage = {"compliance.analyze": "compliance",
                 "conviction.analyze": "conviction",
                 "draft.render": "draft_render"}.get(_task_type(payload), "module")
        if complete_execution(execution_id, "failed", stage, fencing_token, None, exc.code, str(exc),
                              retryable=False, owner=owner):
            _notify_application(execution_id)
        raise
    except RegistryError as exc:
        if complete_execution(execution_id, "failed", running_stage, fencing_token, None,
                              exc.code, str(exc), retryable=exc.code != "INVALID_AS_OF_DATE", owner=owner):
            _notify_application(execution_id)
        raise
    except AmountAggregationError as exc:
        if complete_execution(execution_id, "failed", running_stage, fencing_token, None,
                              exc.code, str(exc), retryable=False, owner=owner):
            _notify_application(execution_id)
        raise
    except ModelError as exc:
        if complete_execution(execution_id, "failed", "model_probe", fencing_token, None, exc.code, str(exc), owner=owner):
            _notify_application(execution_id)
        raise
    except Exception as exc:
        if task_type == "document.parse":
            code, stage, retryable = "DOCUMENT_PARSE_FAILED", "document_parsing", False
        elif task_type == "model.probe":
            code, stage, retryable = "MODEL_FAILED", "model_probe", False
        else:
            code, stage, retryable = "ENGINE_FAILED", "failed", True
        if complete_execution(execution_id, "failed", stage, fencing_token, None, code, str(exc), retryable=retryable, owner=owner):
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
