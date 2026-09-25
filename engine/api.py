from __future__ import annotations

import hashlib
import secrets
import tempfile
from pathlib import Path
from uuid import UUID

import dramatiq
from fastapi import Depends, FastAPI, Header, HTTPException, status

from engine.adapters.sources import SourceSearchUnavailable
from engine.adapters.sources import search as search_sources_adapter
from engine.adapters.t1_contract import build_t1_case_create, build_t1_fact_view, build_t1_module_state
from engine.contracts import (
    ExecutionRequest,
    ExecutionView,
    ImportPackageValidationRequest,
    ImportPackageValidationResponse,
    SourceSearchRequest,
    SourceSearchResponse,
    canonical_input_hash,
)
from engine.import_package import ImportPackageValidationError, load_import_package
from engine.object_store import fetch_object_bytes
from engine.settings import settings
from engine.store import claim_enqueue, create_execution, get_execution, mark_enqueued, release_enqueue

app = FastAPI(title="LexCyber Execution Engine", version="0.8.0")


def require_service_token(x_service_token: str = Header(default="")) -> None:
    if not settings.service_token or not secrets.compare_digest(x_service_token, settings.service_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid service token")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "lexcyber-engine", "version": "0.8.0"}


@app.post("/internal/v1/executions", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_service_token)])
def submit_execution(payload: ExecutionRequest) -> ExecutionView:
    if payload.input_hash != canonical_input_hash(payload.query, payload.case_id, payload.session_id, payload.metadata):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="input hash does not match execution input")
    try:
        view = create_execution(payload.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=503, detail="engine persistence unavailable") from exc
    if (
        str(view.get("task_id")) != str(payload.task_id)
        or view.get("input_hash") != payload.input_hash
        or str(view.get("result_id")) != str(payload.result_id)
        or view.get("result_version") != payload.result_version
        or view.get("result_type") != payload.result_type
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="execution id is already bound to a different request")
    try:
        if claim_enqueue(payload.execution_id):
            execute_task.send(payload.model_dump(mode="json"))
            mark_enqueued(payload.execution_id)
    except Exception as exc:
        release_enqueue(payload.execution_id, str(exc))
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="engine queue unavailable") from exc
    return ExecutionView.model_validate(view)


@app.get("/internal/v1/capabilities", dependencies=[Depends(require_service_token)])
def capabilities_endpoint() -> dict:
    """模块能力声明：family 全部有 approved 规则包才可派发（INV-RULE-002 / INV-GATE-002）。"""
    from engine.rules import registry

    try:
        return registry.capabilities()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="rule registry unavailable") from exc


@app.post("/internal/v1/registry/legal-sources", status_code=status.HTTP_201_CREATED,
          dependencies=[Depends(require_service_token)])
def register_legal_source_endpoint(payload: dict) -> dict:
    from engine.rules.registry import RegistryError, register_legal_source

    try:
        return register_legal_source(payload)
    except RegistryError as exc:
        raise HTTPException(status_code=409, detail=exc.code) from exc


@app.post("/internal/v1/registry/rules", status_code=status.HTTP_201_CREATED,
          dependencies=[Depends(require_service_token)])
def register_rule_endpoint(payload: dict) -> dict:
    from engine.rules.registry import RegistryError, register_rule_package

    try:
        return register_rule_package(payload)
    except RegistryError as exc:
        raise HTTPException(status_code=409, detail=exc.code) from exc


@app.post("/internal/v1/registry/templates", status_code=status.HTTP_201_CREATED,
          dependencies=[Depends(require_service_token)])
def register_template_endpoint(payload: dict) -> dict:
    from engine.rules.registry import RegistryError, register_template

    try:
        return register_template(payload)
    except RegistryError as exc:
        raise HTTPException(status_code=409, detail=exc.code) from exc


@app.post("/internal/v1/registry/signoffs", status_code=status.HTTP_201_CREATED,
          dependencies=[Depends(require_service_token)])
def signoff_endpoint(payload: dict) -> dict:
    from engine.rules.registry import RegistryError, signoff

    try:
        return signoff(
            subject_kind=payload.get("subjectKind"),
            subject_key=payload.get("subjectKey"),
            reviewer=payload.get("reviewer"),
            role=payload.get("role"),
            decision=payload.get("decision"),
            comment=payload.get("comment"),
        )
    except RegistryError as exc:
        raise HTTPException(status_code=409, detail=exc.code) from exc


@app.post("/internal/v1/registry/resolve", dependencies=[Depends(require_service_token)])
def resolve_temporal_endpoint(payload: dict) -> dict:
    from datetime import date as _date

    from engine.rules.registry import resolve_temporal

    def _parse(value):
        return _date.fromisoformat(value) if value else None

    return resolve_temporal(
        payload.get("sourceKey", ""),
        _parse(payload.get("conductDate")),
        _parse(payload.get("judgmentDate")),
    )


@app.get("/internal/v1/executions/{execution_id}", dependencies=[Depends(require_service_token)])
def execution_status(execution_id: UUID) -> ExecutionView:
    try:
        view = get_execution(execution_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="engine persistence unavailable") from exc
    if not view:
        raise HTTPException(status_code=404, detail="execution not found")
    return ExecutionView.model_validate(view)


@app.post("/internal/v1/sources/search", dependencies=[Depends(require_service_token)])
def search_sources(payload: SourceSearchRequest) -> SourceSearchResponse:
    try:
        items = search_sources_adapter(payload.model_dump())
    except SourceSearchUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=exc.code) from exc
    return SourceSearchResponse.model_validate({"items": items})


@app.post(
    "/internal/v1/imports/validate",
    dependencies=[Depends(require_service_token)],
)
def validate_import_package_endpoint(payload: ImportPackageValidationRequest) -> ImportPackageValidationResponse:
    try:
        raw = fetch_object_bytes(payload.storage_key)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="import package storage unavailable") from exc
    actual_hash = hashlib.sha256(raw).hexdigest()
    if actual_hash != payload.raw_sha256:
        return ImportPackageValidationResponse(
            valid=False,
            errors=[{"code": "RAW_HASH_MISMATCH", "path": "$", "message": "raw package hash does not match"}],
        )
    try:
        with tempfile.TemporaryDirectory(prefix="lexcyber-import-") as directory:
            archive_path = Path(directory) / "package.zip"
            archive_path.write_bytes(raw)
            package = load_import_package(archive_path)
    except ImportPackageValidationError as exc:
        return ImportPackageValidationResponse(valid=False, errors=[item.as_dict() for item in exc.issues])
    except Exception as exc:
        return ImportPackageValidationResponse(
            valid=False,
            errors=[{"code": "PACKAGE_READ_FAILED", "path": "$", "message": str(exc)}],
        )

    manifest = package.manifest
    normalized_items: list[dict] = []
    for manifest_item in manifest["items"]:
        item_id = str(manifest_item["item_id"])
        bundle = package.payloads[item_id]
        document_map = {str(item["id"]): str(item["id"]) for item in bundle.get("documents", [])}
        case_create = build_t1_case_create(bundle)
        case_create.setdefault("metadata", {}).update(
            {
                "producerId": manifest["producer_id"],
                "packageId": manifest["package_id"],
                "datasetId": manifest["dataset_id"],
                "datasetRevision": manifest["revision"],
                "externalCaseId": manifest_item["external_case_id"],
            }
        )
        projected = build_t1_case_create(bundle, document_map)
        event_bindings = (((projected.get("metadata") or {}).get("relations") or {}).get("events") or [])
        facts = build_t1_fact_view(
            bundle,
            case_id=f"import-preview-{item_id}",
            document_id_map=document_map,
            status="draft",
        )["items"]
        modules = {
            name: build_t1_module_state(bundle, name, f"import-preview-{item_id}")
            for name in ("compliance", "conviction")
        }
        source_documents = {str(item["id"]): item for item in bundle.get("documents", [])}
        files = []
        for descriptor in manifest_item["files"]:
            item = dict(descriptor)
            document = source_documents.get(str(descriptor["document_id"])) or {}
            item["source_version"] = document.get("source_version")
            files.append(item)
        normalized_items.append(
            {
                "item_id": item_id,
                "external_case_id": manifest_item["external_case_id"],
                "payload_path": manifest_item["payload"]["path"],
                "payload_sha256": manifest_item["payload"]["sha256"],
                "case_create": case_create,
                "event_bindings": event_bindings,
                "facts": facts,
                "modules": modules,
                "files": files,
            }
        )
    return ImportPackageValidationResponse(
        valid=True,
        schema_version=manifest["schema_version"],
        package_id=manifest["package_id"],
        producer_id=manifest["producer_id"],
        dataset_id=manifest["dataset_id"],
        revision=manifest["revision"],
        package_digest=package.package_digest,
        items=normalized_items,
    )


@dramatiq.actor(max_retries=2, time_limit=300_000)
def execute_task(payload: dict) -> None:
    from engine.worker import run_execution

    run_execution(payload)
