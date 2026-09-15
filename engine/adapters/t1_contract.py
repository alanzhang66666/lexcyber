from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any


class T1ContractError(ValueError):
    """Raised when an internal T3 value cannot be safely projected to T1."""


def _organization_id(actor_id: str) -> str:
    if actor_id.startswith("actor-"):
        return f"org-{actor_id.removeprefix('actor-')}"
    return f"org-{actor_id}"


def _locator_text(locator: Mapping[str, Any] | str | None) -> str | None:
    if isinstance(locator, str):
        return locator
    if not locator:
        return None
    for key in ("paragraph", "page"):
        value = locator.get(key)
        if value is not None:
            return f"{key}:{value}"
    start = locator.get("start")
    end = locator.get("end")
    if start is not None and end is not None:
        return f"start:{start};end:{end}"
    if start is not None:
        return f"start:{start}"
    if end is not None:
        return f"end:{end}"
    return None


def _document_id(dataset_document_id: str, document_id_map: Mapping[str, str] | None) -> str:
    if document_id_map and dataset_document_id in document_id_map:
        return document_id_map[dataset_document_id]
    return "doc-pending-upload"


def _evidence_index(bundle: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {str(item["id"]): item for item in bundle.get("evidence", [])}


def _first_evidence(
    evidence_ids: Iterable[str], evidence_by_id: Mapping[str, Mapping[str, Any]]
) -> Mapping[str, Any] | None:
    for evidence_id in evidence_ids:
        evidence = evidence_by_id.get(evidence_id)
        if evidence:
            return evidence
    return None


def build_t1_case_create(
    bundle: Mapping[str, Any], document_id_map: Mapping[str, str] | None = None
) -> dict[str, Any]:
    """Project a rich T3 bundle to T1 CaseCreate without replacing T1 ids.

    Before upload, event document ids use T1's ``doc-pending-upload`` marker.
    Passing ``document_id_map`` replaces dataset document ids with actual
    DocumentView ids after upload.
    """

    people: list[dict[str, str]] = []
    organizations: list[dict[str, str]] = []
    for actor in bundle.get("actors", []):
        actor_id = str(actor["id"])
        if actor.get("type") == "organization":
            organizations.append(
                {
                    "organizationId": _organization_id(actor_id),
                    "label": str(actor.get("name", actor_id)),
                    # Retain the T3 subject identity used by facts and analyses.
                    "actorId": actor_id,
                }
            )
        else:
            people.append(
                {
                    "actorId": actor_id,
                    "label": str(actor.get("name", actor_id)),
                    "roleHint": str(actor.get("role", "")),
                }
            )

    evidence_by_id = _evidence_index(bundle)
    facts_by_id = {str(item["id"]): item for item in bundle.get("facts", [])}
    events: list[dict[str, Any]] = []
    for event in bundle.get("events", []):
        projected: dict[str, Any] = {
            "eventId": str(event["id"]),
            "stage": str(event.get("stage", "")),
            "actorId": str(event.get("actor_id", "")),
            "occurredOn": str(event.get("date", "")),
        }
        evidence_ids: list[str] = []
        for fact_id in event.get("fact_ids", []):
            evidence_ids.extend(facts_by_id.get(str(fact_id), {}).get("evidence_ids", []))
        evidence = _first_evidence(evidence_ids, evidence_by_id)
        if evidence:
            projected["documentId"] = _document_id(str(evidence["document_id"]), document_id_map)
            locator = _locator_text(evidence.get("locator"))
            if locator:
                projected["locator"] = locator
        events.append(projected)

    links = [
        {
            "fromActorId": str(item["from_id"]),
            "toActorId": str(item["to_id"]),
            "type": str(item.get("type", "")),
        }
        for item in bundle.get("relationships", [])
    ]
    organization_ids = {str(actor["id"]) for actor in bundle.get("actors", []) if actor.get("type") == "organization"}
    accounts: list[dict[str, Any]] = []
    for account in bundle.get("accounts", []):
        actor_ids = [str(item) for item in account.get("controller_ids") or account.get("actor_ids") or []]
        projected_account: dict[str, Any] = {"accountId": str(account["id"])}
        organization_id = next(
            (_organization_id(actor_id) for actor_id in actor_ids if actor_id in organization_ids),
            None,
        )
        if organization_id:
            projected_account["organizationId"] = organization_id
        if actor_ids:
            projected_account["actorIds"] = actor_ids
        if account.get("type"):
            projected_account["type"] = str(account["type"])
        if account.get("jurisdiction"):
            projected_account["jurisdiction"] = str(account["jurisdiction"])
        accounts.append(projected_account)

    connections: list[dict[str, Any]] = []
    for item in bundle.get("jurisdiction_connections", []):
        projected_connection: dict[str, Any] = {
            "connectionId": str(item["id"]),
            "type": str(item.get("type", "")),
            "value": str(item.get("value", "")),
        }
        if item.get("verification_status"):
            projected_connection["verificationStatus"] = str(item["verification_status"])
        if item.get("evidence_ids"):
            projected_connection["evidenceIds"] = [str(value) for value in item["evidence_ids"]]
        connections.append(projected_connection)

    metadata: dict[str, Any] = {
        # PR5 froze datasetCaseId as the external A/B/C dataset key.
        "datasetCaseId": str(bundle.get("case_code", "")),
        "t3BundleId": str(bundle.get("case_id", "")),
        "relations": {
            "actors": people,
            "organizations": organizations,
            "accounts": accounts,
            "events": events,
            # metadata is intentionally extensible; keep objective T3 links.
            "links": links,
            "jurisdictionConnections": connections,
        },
    }
    if bundle.get("source_version_binding") is not None:
        metadata["sourceVersionBinding"] = bundle.get("source_version_binding")
    procedure_stage = bundle.get("procedure_stage")
    if procedure_stage is None:
        procedure_stage = bundle.get("procedureStage")
    if procedure_stage is not None and str(procedure_stage).strip():
        metadata["procedureStage"] = procedure_stage

    return {
        "title": str(bundle.get("title", "")),
        "jurisdiction": str(bundle.get("jurisdiction", "CN")),
        # T1 asOfDate is the legal-analysis date; conduct dates remain events.
        "asOfDate": str(bundle.get("analysis_as_of_date", "")),
        "metadata": metadata,
    }


def _fact_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def build_t1_fact_view(
    bundle: Mapping[str, Any],
    *,
    case_id: str,
    document_id_map: Mapping[str, str],
    status: str = "draft",
    item_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Build T1 ``case.facts.v1`` while keeping item review state internal.

    T1 owns ``case_id`` and only accepts aggregate ``draft``/``confirmed``.
    Confirmation is therefore allowed only for an explicit selection whose T3
    items are already individually confirmed by a human.
    """

    if not case_id or case_id == bundle.get("case_id"):
        raise T1ContractError("case_id must be the server CaseView.id, not the T3 dataset case id")
    if status not in {"draft", "confirmed"}:
        raise T1ContractError(f"unsupported T1 fact status: {status}")
    selected_ids = set(item_ids) if item_ids is not None else None
    if status == "confirmed" and selected_ids is None:
        raise T1ContractError("confirmed projection requires an explicit item_ids selection")

    evidence_by_id = _evidence_index(bundle)
    source_items = [*bundle.get("facts", []), *bundle.get("amounts", [])]
    projected_items: list[dict[str, str]] = []
    found_ids: set[str] = set()
    for item in source_items:
        item_id = str(item["id"])
        if selected_ids is not None and item_id not in selected_ids:
            continue
        found_ids.add(item_id)
        if status == "confirmed" and item.get("verification_status") != "confirmed":
            raise T1ContractError(f"cannot confirm unconfirmed T3 item: {item_id}")
        evidence = _first_evidence(item.get("evidence_ids", []), evidence_by_id)
        if not evidence:
            raise T1ContractError(f"T1 fact requires evidence: {item_id}")
        dataset_document_id = str(evidence["document_id"])
        if dataset_document_id not in document_id_map:
            raise T1ContractError(f"missing uploaded DocumentView.id for {dataset_document_id}")
        locator = _locator_text(evidence.get("locator"))
        if not locator:
            raise T1ContractError(f"T1 fact requires a string locator: {item_id}")
        projected_item: dict[str, str] = {
            "id": item_id,
            "key": str(item.get("type") or item.get("kind") or "unclassified"),
            "value": _fact_value(item.get("value")),
            "locator": locator,
            "sourceDocumentId": document_id_map[dataset_document_id],
        }
        if item.get("verification_status"):
            projected_item["verificationStatus"] = str(item["verification_status"])
        if item.get("source_version"):
            projected_item["sourceVersion"] = str(item["source_version"])
        projected_items.append(projected_item)
    if selected_ids is not None and found_ids != selected_ids:
        missing = ", ".join(sorted(selected_ids - found_ids))
        raise T1ContractError(f"unknown T3 fact item ids: {missing}")

    return {
        "caseId": case_id,
        "schemaVersion": "case.facts.v1",
        "status": status,
        "items": projected_items,
    }


def build_t1_module_state(bundle: Mapping[str, Any], module: str, case_id: str) -> dict[str, Any]:
    """Project one T3 analysis block into an opaque T1 module shell."""

    if module not in {"compliance", "conviction"}:
        raise T1ContractError(f"unsupported T1 module: {module}")
    if not case_id or case_id == bundle.get("case_id"):
        raise T1ContractError("case_id must be the server CaseView.id, not the T3 dataset case id")
    analysis = (bundle.get("analyses") or {}).get(module)
    content = dict(analysis) if isinstance(analysis, Mapping) else {}
    applicability = content.get("applicability") or "unknown"
    binding = bundle.get("source_version_binding")
    source_version = None
    if isinstance(binding, str) and binding.strip():
        source_version = binding
    elif binding is not None:
        source_version = json.dumps(binding, ensure_ascii=False, sort_keys=True)
    return {
        "caseId": case_id,
        "module": module,
        "applicability": str(applicability),
        "content": content,
        "sourceVersion": source_version,
        "version": 0,
    }


def map_sentencing_result_to_t1(
    result: Mapping[str, Any], *, case_id: str, dataset_case_id: str | None = None
) -> dict[str, Any]:
    """Separate T1 TaskView status from T3's content-level analysis status."""

    if not case_id or case_id == result.get("case_id"):
        raise T1ContractError("case_id must be the server CaseView.id, not the T3 dataset case id")
    human_review_required = bool(result.get("human_review_required"))
    task_status = "waiting_review" if human_review_required else "completed"
    content = {
        "caseId": case_id,
        "datasetCaseId": dataset_case_id or result.get("case_id"),
        "t3BundleId": result.get("case_id"),
        "actorId": result.get("actor_id"),
        "analysisStatus": result.get("status"),
        "ruleVersion": result.get("rule_version"),
        "sourceIds": list(result.get("source_ids", [])),
        "inputSnapshot": dict(result.get("input_snapshot", {})),
        "termMonths": result.get("term_months"),
        "fine": result.get("fine"),
        "steps": list(result.get("steps", [])),
        "blockers": list(result.get("blockers", [])),
        "warnings": list(result.get("warnings", [])),
        "humanReviewRequired": human_review_required,
    }
    return {"taskStatus": task_status, "content": content}
