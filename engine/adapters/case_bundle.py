from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEMO_ROOT = Path(__file__).resolve().parents[2] / "demo_cases" / "three_case_demo"
INDEX_PATH = DEMO_ROOT / "index.json"


def _issue(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_case_bundle(case_id: str, root: Path | None = None) -> dict[str, Any]:
    """Load a case by stable demo id; callers never need repository-relative guesses."""

    dataset_root = root or DEMO_ROOT
    index = _read_json(dataset_root / "index.json")
    matches = [item for item in index.get("cases", []) if item.get("case_id") == case_id or item.get("case_code") == case_id]
    if not matches:
        raise KeyError(f"unsupported demo case: {case_id}")
    return _read_json(dataset_root / matches[0]["bundle"])


def validate_case_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    """Validate referential integrity and review gates of one T3 case bundle."""

    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    required = ("schema_version", "case_id", "case_code", "title", "documents", "actors", "evidence", "facts", "events", "analyses")
    for field in required:
        if field not in bundle:
            errors.append(_issue("required_field_missing", field, f"required field is missing: {field}"))

    def collect_ids(field: str) -> set[str]:
        values: set[str] = set()
        for position, item in enumerate(bundle.get(field, [])):
            item_id = item.get("id") if isinstance(item, dict) else None
            if not item_id:
                errors.append(_issue("id_missing", f"{field}[{position}].id", "item id is required"))
            elif item_id in values:
                errors.append(_issue("duplicate_id", f"{field}[{position}].id", f"duplicate id: {item_id}"))
            else:
                values.add(item_id)
        return values

    document_ids = collect_ids("documents")
    actor_ids = collect_ids("actors")
    evidence_ids = collect_ids("evidence")
    fact_ids = collect_ids("facts")
    event_ids = collect_ids("events")
    amount_ids = collect_ids("amounts")
    legal_source_ids = set(bundle.get("legal_source_ids", []))

    if len(document_ids) < 2:
        errors.append(_issue("insufficient_documents", "documents", "a demo case must declare at least two source documents"))
    evidentiary_docs = [item for item in bundle.get("documents", []) if item.get("role") == "case_material"]
    if len(evidentiary_docs) < 2:
        warnings.append(
            _issue(
                "insufficient_evidentiary_documents",
                "documents",
                "fewer than two documents are case materials; benchmark annotations do not count as evidence",
            )
        )

    for position, item in enumerate(bundle.get("evidence", [])):
        if item.get("document_id") not in document_ids:
            errors.append(_issue("unknown_document", f"evidence[{position}].document_id", str(item.get("document_id"))))
        locator = item.get("locator") or {}
        if not any(locator.get(key) is not None for key in ("page", "paragraph", "start", "end")):
            errors.append(_issue("locator_missing", f"evidence[{position}].locator", "evidence must be traceable to a source location"))

    allowed_verification = {"candidate", "baseline_asserted", "confirmed", "rejected", "conflicted"}
    for position, item in enumerate(bundle.get("facts", [])):
        if item.get("actor_id") and item["actor_id"] not in actor_ids:
            errors.append(_issue("unknown_actor", f"facts[{position}].actor_id", item["actor_id"]))
        unknown_evidence = set(item.get("evidence_ids", [])) - evidence_ids
        if unknown_evidence:
            errors.append(_issue("unknown_evidence", f"facts[{position}].evidence_ids", ", ".join(sorted(unknown_evidence))))
        if item.get("verification_status") not in allowed_verification:
            errors.append(_issue("verification_status_invalid", f"facts[{position}].verification_status", str(item.get("verification_status"))))

    for position, item in enumerate(bundle.get("events", [])):
        if item.get("actor_id") and item["actor_id"] not in actor_ids:
            errors.append(_issue("unknown_actor", f"events[{position}].actor_id", item["actor_id"]))
        unknown_facts = set(item.get("fact_ids", [])) - fact_ids
        if unknown_facts:
            errors.append(_issue("unknown_fact", f"events[{position}].fact_ids", ", ".join(sorted(unknown_facts))))

    for position, relationship in enumerate(bundle.get("relationships", [])):
        unknown_actors = {relationship.get("from_id"), relationship.get("to_id")} - actor_ids
        if unknown_actors:
            errors.append(_issue("unknown_actor", f"relationships[{position}]", ", ".join(sorted(str(item) for item in unknown_actors))))

    for position, connection in enumerate(bundle.get("jurisdiction_connections", [])):
        unknown_evidence = set(connection.get("evidence_ids", [])) - evidence_ids
        if unknown_evidence:
            errors.append(_issue("unknown_evidence", f"jurisdiction_connections[{position}].evidence_ids", ", ".join(sorted(unknown_evidence))))

    for analysis_name, analysis in (bundle.get("analyses") or {}).items():
        if not isinstance(analysis, dict):
            errors.append(_issue("analysis_invalid", f"analyses.{analysis_name}", "analysis must be an object"))
            continue
        for position, path in enumerate(analysis.get("candidate_paths", [])):
            if path.get("actor_id") and path["actor_id"] not in actor_ids:
                errors.append(_issue("unknown_actor", f"analyses.{analysis_name}.candidate_paths[{position}].actor_id", path["actor_id"]))
            unknown_support = set(path.get("supporting_evidence_ids", [])) - evidence_ids
            unknown_contrary = set(path.get("contrary_evidence_ids", [])) - evidence_ids
            if unknown_support or unknown_contrary:
                errors.append(
                    _issue(
                        "unknown_evidence",
                        f"analyses.{analysis_name}.candidate_paths[{position}]",
                        ", ".join(sorted(unknown_support | unknown_contrary)),
                    )
                )
            unknown_sources = set(path.get("legal_source_ids", [])) - legal_source_ids
            if unknown_sources:
                errors.append(
                    _issue(
                        "unknown_legal_source",
                        f"analyses.{analysis_name}.candidate_paths[{position}].legal_source_ids",
                        ", ".join(sorted(unknown_sources)),
                    )
                )
        for position, item in enumerate(analysis.get("checklist", [])):
            unknown_evidence = set(item.get("evidence_ids", [])) - evidence_ids
            if unknown_evidence:
                errors.append(
                    _issue(
                        "unknown_evidence",
                        f"analyses.{analysis_name}.checklist[{position}].evidence_ids",
                        ", ".join(sorted(unknown_evidence)),
                    )
                )

    for position, item in enumerate(bundle.get("amounts", [])):
        if not isinstance(item.get("value"), (int, float)) or item.get("value", -1) < 0:
            errors.append(_issue("amount_invalid", f"amounts[{position}].value", "amount must be a non-negative number"))
        unknown_evidence = set(item.get("evidence_ids", [])) - evidence_ids
        if unknown_evidence:
            errors.append(_issue("unknown_evidence", f"amounts[{position}].evidence_ids", ", ".join(sorted(unknown_evidence))))

    sentencing = bundle.get("sentencing") or {}
    for position, baseline in enumerate(sentencing.get("actor_baselines", [])):
        if baseline.get("actor_id") not in actor_ids:
            errors.append(_issue("unknown_actor", f"sentencing.actor_baselines[{position}].actor_id", str(baseline.get("actor_id"))))
        unknown_amounts = set(baseline.get("amount_ids", [])) - amount_ids
        if unknown_amounts:
            errors.append(_issue("unknown_amount", f"sentencing.actor_baselines[{position}].amount_ids", ", ".join(sorted(unknown_amounts))))
        if baseline.get("legal_review_status") != "approved":
            warnings.append(
                _issue(
                    "sentencing_not_approved",
                    f"sentencing.actor_baselines[{position}]",
                    "calculator will fail closed until a qualified legal reviewer approves this baseline",
                )
            )
        unknown_sources = set(baseline.get("source_ids", [])) - legal_source_ids
        if unknown_sources:
            errors.append(
                _issue(
                    "unknown_legal_source",
                    f"sentencing.actor_baselines[{position}].source_ids",
                    ", ".join(sorted(unknown_sources)),
                )
            )

    missing_items = bundle.get("missing_items", [])
    if missing_items:
        warnings.append(_issue("open_missing_items", "missing_items", f"{len(missing_items)} item(s) still require confirmation"))

    return {
        "case_id": bundle.get("case_id"),
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "counts": {
            "documents": len(document_ids),
            "actors": len(actor_ids),
            "evidence": len(evidence_ids),
            "facts": len(fact_ids),
            "events": len(event_ids),
            "amounts": len(amount_ids),
        },
    }


def validate_case_dataset(root: Path | None = None) -> dict[str, Any]:
    dataset_root = root or DEMO_ROOT
    index = _read_json(dataset_root / "index.json")
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    seen_codes: set[str] = set()
    for position, item in enumerate(index.get("cases", [])):
        case_id = item.get("case_id")
        case_code = item.get("case_code")
        if case_id in seen_ids or case_code in seen_codes:
            errors.append(_issue("duplicate_case", f"cases[{position}]", f"duplicate case identity: {case_id}/{case_code}"))
            continue
        seen_ids.add(case_id)
        seen_codes.add(case_code)
        bundle_path = dataset_root / str(item.get("bundle", ""))
        if not bundle_path.is_file():
            errors.append(_issue("bundle_missing", f"cases[{position}].bundle", str(bundle_path)))
            continue
        bundle = _read_json(bundle_path)
        if bundle.get("case_id") != case_id or bundle.get("case_code") != case_code:
            errors.append(_issue("index_identity_mismatch", f"cases[{position}]", str(bundle_path)))
        results.append(validate_case_bundle(bundle))
    return {
        "valid": not errors and len(results) == 3 and all(item["valid"] for item in results),
        "errors": errors,
        "cases": results,
        "expected_case_count": 3,
        "actual_case_count": len(results),
    }
