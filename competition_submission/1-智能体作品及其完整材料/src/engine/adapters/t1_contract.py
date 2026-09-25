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


MODULE_CONTENT_SCHEMA = "case.module.content.v1"


def _str_list(values: Any) -> list[str]:
    if not values:
        return []
    return [str(item) for item in values]


def _alias(item: dict[str, Any], camel: str, snake: str) -> None:
    if camel in item:
        item[snake] = item[camel]


def _fact_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _source_version_string(binding: Any) -> str | None:
    if isinstance(binding, str) and binding.strip():
        return binding
    if binding is not None:
        return json.dumps(binding, ensure_ascii=False, sort_keys=True)
    return None


def _project_jurisdiction_connections(bundle: Mapping[str, Any]) -> list[dict[str, Any]]:
    connections: list[dict[str, Any]] = []
    for item in bundle.get("jurisdiction_connections", []):
        projected: dict[str, Any] = {
            "connectionId": str(item["id"]),
            "type": str(item.get("type", "")),
            "value": str(item.get("value", "")),
        }
        if item.get("verification_status"):
            projected["verificationStatus"] = str(item["verification_status"])
            _alias(projected, "verificationStatus", "verification_status")
        if item.get("evidence_ids"):
            projected["evidenceIds"] = _str_list(item["evidence_ids"])
            _alias(projected, "evidenceIds", "evidence_ids")
        connections.append(projected)
    return connections


def _project_amounts(bundle: Mapping[str, Any]) -> list[dict[str, Any]]:
    amounts: list[dict[str, Any]] = []
    for item in bundle.get("amounts", []):
        projected: dict[str, Any] = {
            "id": str(item["id"]),
            "kind": str(item.get("kind", "")),
            "label": str(item.get("label", "")),
            "value": item.get("value"),
            "currency": str(item.get("currency") or "CNY"),
        }
        if item.get("verification_status"):
            projected["verificationStatus"] = str(item["verification_status"])
            _alias(projected, "verificationStatus", "verification_status")
        projected["evidenceIds"] = _str_list(item.get("evidence_ids"))
        _alias(projected, "evidenceIds", "evidence_ids")
        if item.get("classification_status"):
            projected["classificationStatus"] = str(item["classification_status"])
            _alias(projected, "classificationStatus", "classification_status")
        amounts.append(projected)
    return amounts


def _expand_module_facts(bundle: Mapping[str, Any], fact_ids: Any) -> list[dict[str, Any]]:
    facts_by_id = {str(item["id"]): item for item in bundle.get("facts", [])}
    expanded: list[dict[str, Any]] = []
    for fact_id in fact_ids or []:
        item = facts_by_id.get(str(fact_id))
        if not item:
            expanded.append({"id": str(fact_id)})
            continue
        projected: dict[str, Any] = {
            "id": str(item["id"]),
            "statement": _fact_value(item.get("value")),
        }
        if item.get("type"):
            projected["type"] = str(item["type"])
        if item.get("actor_id"):
            projected["actorId"] = str(item["actor_id"])
        if item.get("stage"):
            projected["stage"] = str(item["stage"])
        if item.get("verification_status"):
            projected["verificationStatus"] = str(item["verification_status"])
            _alias(projected, "verificationStatus", "verification_status")
        projected["evidenceIds"] = _str_list(item.get("evidence_ids"))
        _alias(projected, "evidenceIds", "evidence_ids")
        expanded.append(projected)
    return expanded


def _project_candidate_paths(paths: Any) -> list[dict[str, Any]]:
    projected_paths: list[dict[str, Any]] = []
    for item in paths or []:
        if not isinstance(item, Mapping):
            continue
        projected: dict[str, Any] = {
            "id": str(item.get("id", "")),
            "label": str(item.get("label") or item.get("title") or ""),
        }
        if item.get("actor_id"):
            projected["actorId"] = str(item["actor_id"])
        if item.get("baseline_position"):
            projected["baselinePosition"] = str(item["baseline_position"])
            _alias(projected, "baselinePosition", "baseline_position")
        projected["supportingEvidenceIds"] = _str_list(item.get("supporting_evidence_ids"))
        projected["contraryEvidenceIds"] = _str_list(item.get("contrary_evidence_ids"))
        projected["legalSourceIds"] = _str_list(item.get("legal_source_ids"))
        _alias(projected, "supportingEvidenceIds", "supporting_evidence_ids")
        _alias(projected, "contraryEvidenceIds", "contrary_evidence_ids")
        _alias(projected, "legalSourceIds", "legal_source_ids")
        projected_paths.append(projected)
    return projected_paths


def _project_checklist(items: Any) -> list[dict[str, Any]]:
    checklist: list[dict[str, Any]] = []
    for item in items or []:
        if not isinstance(item, Mapping):
            continue
        projected: dict[str, Any] = {
            "category": str(item.get("category", "")),
            "status": str(item.get("status", "")),
        }
        projected["evidenceIds"] = _str_list(item.get("evidence_ids") or item.get("evidenceIds"))
        _alias(projected, "evidenceIds", "evidence_ids")
        checklist.append(projected)
    return checklist


def _project_missing_items(bundle: Mapping[str, Any]) -> list[dict[str, Any]]:
    missing: list[dict[str, Any]] = []
    for item in bundle.get("missing_items", []):
        missing.append(
            {
                "id": str(item.get("id", "")),
                "severity": str(item.get("severity", "")),
                "description": str(item.get("description", "")),
            }
        )
    return missing


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

    connections = _project_jurisdiction_connections(bundle)
    amounts = _project_amounts(bundle)

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
    if amounts:
        metadata["amounts"] = amounts
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
    """Project one T3 analysis block into frozen T1 module-shell content.

    Content is still opaque to Java (not validated as law). Keys are the public
    ``case.module.content.v1`` shape plus snake_case aliases T2 already reads.
    """

    if module not in {"compliance", "conviction"}:
        raise T1ContractError(f"unsupported T1 module: {module}")
    if not case_id or case_id == bundle.get("case_id"):
        raise T1ContractError("case_id must be the server CaseView.id, not the T3 dataset case id")
    analysis = (bundle.get("analyses") or {}).get(module)
    analysis = dict(analysis) if isinstance(analysis, Mapping) else {}
    applicability = analysis.get("applicability") or "unknown"
    binding = bundle.get("source_version_binding")
    content: dict[str, Any] = {
        "schemaVersion": MODULE_CONTENT_SCHEMA,
        "applicability": str(applicability),
    }
    if analysis.get("result_status"):
        content["resultStatus"] = str(analysis["result_status"])
        _alias(content, "resultStatus", "result_status")
    if analysis.get("legal_review_status"):
        content["legalReviewStatus"] = str(analysis["legal_review_status"])
        _alias(content, "legalReviewStatus", "legal_review_status")
    if analysis.get("note"):
        content["note"] = str(analysis["note"])
    facts = _expand_module_facts(bundle, analysis.get("facts"))
    if facts:
        content["facts"] = facts
    paths = _project_candidate_paths(analysis.get("candidate_paths") or analysis.get("candidatePaths"))
    if paths:
        content["candidatePaths"] = paths
        _alias(content, "candidatePaths", "candidate_paths")
    checklist = _project_checklist(analysis.get("checklist"))
    if checklist:
        content["checklist"] = checklist
    amounts = _project_amounts(bundle)
    if amounts:
        content["amounts"] = amounts
    missing = _project_missing_items(bundle)
    if missing:
        content["missingItems"] = missing
        _alias(content, "missingItems", "missing_items")
    if analysis.get("jurisdiction_status"):
        content["jurisdictionStatus"] = str(analysis["jurisdiction_status"])
        _alias(content, "jurisdictionStatus", "jurisdiction_status")
    if analysis.get("jurisdiction_source_ids"):
        content["jurisdictionSourceIds"] = _str_list(analysis["jurisdiction_source_ids"])
        _alias(content, "jurisdictionSourceIds", "jurisdiction_source_ids")
    connections = _project_jurisdiction_connections(bundle)
    if module == "conviction" and connections:
        content["jurisdictionConnections"] = connections
    if binding is not None:
        content["sourceVersionBinding"] = binding
    return {
        "caseId": case_id,
        "module": module,
        "applicability": str(applicability),
        "content": content,
        "sourceVersion": _source_version_string(binding),
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
        "calculationMode": result.get("calculation_mode"),
        "ruleVersion": result.get("rule_version"),
        "sourceIds": list(result.get("source_ids", [])),
        "reviewedRuleOutline": dict(result.get("reviewed_rule_outline", {})),
        "inputSnapshot": dict(result.get("input_snapshot", {})),
        "termMonths": result.get("term_months"),
        "termRangeMonths": result.get("term_range_months"),
        "termLowerKind": result.get("term_lower_kind"),
        "termUpperKind": result.get("term_upper_kind"),
        "fine": result.get("fine"),
        "fineRangeCny": result.get("fine_range_cny"),
        "recoveryCny": result.get("recovery_cny"),
        "steps": list(result.get("steps", [])),
        "blockers": list(result.get("blockers", [])),
        "warnings": list(result.get("warnings", [])),
        "humanReviewRequired": human_review_required,
    }
    return {"taskStatus": task_status, "content": content}
