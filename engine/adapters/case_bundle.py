from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

DEMO_ROOT = Path(__file__).resolve().parents[2] / "demo_cases" / "three_case_demo"
CONTRACT_SCHEMA_ROOT = Path(__file__).resolve().parents[2] / "contracts" / "schemas"
INDEX_PATH = DEMO_ROOT / "index.json"
TEMPLATE_REGISTRY_PATH = DEMO_ROOT / "document-templates.json"
BASELINE_SCENARIOS_PATH = DEMO_ROOT / "baseline-scenarios.json"
LEGAL_SOURCE_CATALOG_PATH = Path(__file__).resolve().parent / "legal_sources.json"
INDEX_SCHEMA_PATH = CONTRACT_SCHEMA_ROOT / "collaboration-case-index.schema.json"
BUNDLE_SCHEMA_PATH = CONTRACT_SCHEMA_ROOT / "collaboration-case-bundle.schema.json"
BASELINE_SCHEMA_PATH = CONTRACT_SCHEMA_ROOT / "three-case-baseline.schema.json"


def _issue(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _json_path(prefix: str, parts: Any) -> str:
    path = prefix
    for part in parts:
        path += f"[{part}]" if isinstance(part, int) else (f".{part}" if path else str(part))
    return path or "$"


def _schema_issues(instance: Any, schema_path: Path, prefix: str = "") -> list[dict[str, str]]:
    schema = _read_json(schema_path)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        _issue("schema_validation_failed", _json_path(prefix, error.absolute_path), error.message)
        for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.absolute_path))
    ]


def load_case_dataset_index(root: Path | None = None) -> dict[str, Any]:
    """Load the collaboration identity manifest without weakening validation."""

    dataset_root = root or DEMO_ROOT
    return _read_json(dataset_root / "index.json")


def load_case_bundle(case_id: str, root: Path | None = None) -> dict[str, Any]:
    """Load a case by stable demo id; callers never need repository-relative guesses."""

    dataset_root = root or DEMO_ROOT
    index = load_case_dataset_index(dataset_root)
    matches = [item for item in index.get("cases", []) if item.get("case_id") == case_id or item.get("case_code") == case_id]
    if not matches:
        raise KeyError(f"unsupported demo case: {case_id}")
    if len(matches) > 1:
        raise KeyError(f"ambiguous demo case identity: {case_id}")
    return _read_json(dataset_root / matches[0]["bundle"])


def load_document_template_registry(root: Path | None = None) -> dict[str, Any]:
    """Load the versioned legal-document template contract used by the demo bundles."""

    dataset_root = root or DEMO_ROOT
    return _read_json(dataset_root / "document-templates.json")


def load_three_case_baseline(root: Path | None = None) -> dict[str, Any]:
    """Load the versioned T3 normal/blocking scenario handoff."""

    dataset_root = root or DEMO_ROOT
    return _read_json(dataset_root / "baseline-scenarios.json")


def validate_document_template_registry(registry: dict[str, Any]) -> dict[str, Any]:
    """Validate template identities, source fingerprints, and fail-closed generation policy."""

    errors: list[dict[str, str]] = []
    templates = registry.get("templates", [])
    expected_types = {"prosecution", "sentencing_recommendation", "non_prosecution"}
    seen_ids: set[str] = set()
    seen_types: set[str] = set()

    if registry.get("schema_version") != "lexcyber.document-template-registry.v1":
        errors.append(_issue("template_schema_invalid", "schema_version", str(registry.get("schema_version"))))
    policy = registry.get("generation_policy") or {}
    for field in ("confirmed_values_only", "unresolved_placeholder_blocks_approval", "human_review_required"):
        if policy.get(field) is not True:
            errors.append(_issue("template_policy_unsafe", f"generation_policy.{field}", "must be true"))

    for position, template in enumerate(templates):
        template_id = template.get("id")
        document_type = template.get("document_type")
        if not template_id or template_id in seen_ids:
            errors.append(_issue("template_id_invalid", f"templates[{position}].id", str(template_id)))
        else:
            seen_ids.add(template_id)
        if document_type not in expected_types or document_type in seen_types:
            errors.append(_issue("template_type_invalid", f"templates[{position}].document_type", str(document_type)))
        else:
            seen_types.add(document_type)
        sha256 = template.get("sha256", "")
        if len(sha256) != 64 or any(character not in "0123456789abcdef" for character in sha256):
            errors.append(_issue("template_hash_invalid", f"templates[{position}].sha256", str(sha256)))
        if not template.get("required_fields"):
            errors.append(_issue("template_fields_missing", f"templates[{position}].required_fields", "required fields are empty"))
        if template.get("mapping_status") not in {"structure_extracted_pending_legal_owner_approval", "approved"}:
            errors.append(_issue("template_mapping_status_invalid", f"templates[{position}].mapping_status", str(template.get("mapping_status"))))

    if seen_types != expected_types:
        errors.append(_issue("template_types_incomplete", "templates", ", ".join(sorted(expected_types - seen_types))))
    return {"valid": not errors, "errors": errors, "template_count": len(templates)}


def validate_case_bundle(bundle: dict[str, Any], template_registry: dict[str, Any] | None = None) -> dict[str, Any]:
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
    if not evidentiary_docs:
        errors.append(
            _issue(
                "case_material_missing",
                "documents",
                "at least one case material is required; annotations and review summaries are not evidence",
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

    for position, account in enumerate(bundle.get("accounts", [])):
        linked_actors = set(account.get("controller_ids") or account.get("actor_ids") or [])
        unknown_actors = linked_actors - actor_ids
        if unknown_actors:
            errors.append(
                _issue("unknown_actor", f"accounts[{position}]", ", ".join(sorted(unknown_actors)))
            )

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
        unknown_facts = set(analysis.get("facts", [])) - fact_ids
        if unknown_facts:
            errors.append(
                _issue(
                    "unknown_fact",
                    f"analyses.{analysis_name}.facts",
                    ", ".join(sorted(unknown_facts)),
                )
            )
        unknown_jurisdiction_sources = set(analysis.get("jurisdiction_source_ids", [])) - legal_source_ids
        if unknown_jurisdiction_sources:
            errors.append(
                _issue(
                    "unknown_legal_source",
                    f"analyses.{analysis_name}.jurisdiction_source_ids",
                    ", ".join(sorted(unknown_jurisdiction_sources)),
                )
            )
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
        included_in_amount_id = item.get("included_in_amount_id")
        if included_in_amount_id and included_in_amount_id not in amount_ids:
            errors.append(
                _issue(
                    "unknown_parent_amount",
                    f"amounts[{position}].included_in_amount_id",
                    str(included_in_amount_id),
                )
            )
        if included_in_amount_id == item.get("id"):
            errors.append(
                _issue(
                    "self_included_amount",
                    f"amounts[{position}].included_in_amount_id",
                    "an amount cannot be included in itself",
                )
            )
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
        baseline_amount_ids = set(baseline.get("amount_ids", []))
        double_counted_components = {
            item["id"]
            for item in bundle.get("amounts", [])
            if item.get("id") in baseline_amount_ids and item.get("included_in_amount_id") in baseline_amount_ids
        }
        if double_counted_components:
            errors.append(
                _issue(
                    "amount_component_double_counted",
                    f"sentencing.actor_baselines[{position}].amount_ids",
                    ", ".join(sorted(double_counted_components)),
                )
            )
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
        calculation_rule = baseline.get("calculation_rule")
        if calculation_rule is not None:
            if not isinstance(calculation_rule, dict):
                errors.append(
                    _issue(
                        "sentencing_rule_invalid",
                        f"sentencing.actor_baselines[{position}].calculation_rule",
                        "calculation_rule must be an object",
                    )
                )
            else:
                rule_path = f"sentencing.actor_baselines[{position}].calculation_rule"
                if calculation_rule.get("source_document_id") not in document_ids:
                    errors.append(
                        _issue(
                            "unknown_document",
                            f"{rule_path}.source_document_id",
                            str(calculation_rule.get("source_document_id")),
                        )
                    )
                unknown_rule_sources = set(calculation_rule.get("source_ids", [])) - legal_source_ids
                if unknown_rule_sources:
                    errors.append(
                        _issue(
                            "unknown_legal_source",
                            f"{rule_path}.source_ids",
                            ", ".join(sorted(unknown_rule_sources)),
                        )
                    )
                if not calculation_rule.get("execution_blockers") and calculation_rule.get("legal_review_status") != "approved":
                    errors.append(
                        _issue(
                            "sentencing_rule_blockers_missing",
                            f"{rule_path}.execution_blockers",
                            "a non-approved rule outline must explain why execution remains blocked",
                        )
                    )

    missing_items = bundle.get("missing_items", [])
    if missing_items:
        warnings.append(_issue("open_missing_items", "missing_items", f"{len(missing_items)} item(s) still require confirmation"))

    document_fields = bundle.get("document_fields") or {}
    registry = template_registry or load_document_template_registry()
    templates_by_id = {item.get("id"): item for item in registry.get("templates", [])}
    referenced_template_ids = document_fields.get("template_ids", [])
    unknown_template_ids = set(referenced_template_ids) - set(templates_by_id)
    if unknown_template_ids:
        errors.append(_issue("unknown_document_template", "document_fields.template_ids", ", ".join(sorted(unknown_template_ids))))
    referenced_types = {
        templates_by_id[template_id].get("document_type")
        for template_id in referenced_template_ids
        if template_id in templates_by_id
    }
    missing_selected_types = set(document_fields.get("selected_types", [])) - referenced_types
    if missing_selected_types:
        errors.append(_issue("document_template_type_unmapped", "document_fields.selected_types", ", ".join(sorted(missing_selected_types))))
    if document_fields.get("template_legal_review_status") != "approved":
        warnings.append(
            _issue(
                "document_template_mapping_not_approved",
                "document_fields.template_legal_review_status",
                "source templates are registered, but field mapping and conditional branches still require legal-owner approval",
            )
        )

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


def validate_three_case_baseline(root: Path | None = None) -> dict[str, Any]:
    """Validate T3 identities, source timing, negative paths, and T1 trace fields."""

    dataset_root = root or DEMO_ROOT
    baseline = load_three_case_baseline(dataset_root)
    schema_errors = _schema_issues(baseline, BASELINE_SCHEMA_PATH, "baseline-scenarios.json")
    index = load_case_dataset_index(dataset_root)
    source_catalog = _read_json(LEGAL_SOURCE_CATALOG_PATH)
    sources_by_id = {item.get("id"): item for item in source_catalog.get("sources", [])}
    results: list[dict[str, Any]] = []
    all_errors: list[dict[str, str]] = list(schema_errors)
    seen_codes: set[str] = set()

    if baseline.get("dataset_id") != index.get("dataset_id"):
        all_errors.append(
            _issue(
                "baseline_dataset_mismatch",
                "baseline-scenarios.json.dataset_id",
                f"expected {index.get('dataset_id')}, got {baseline.get('dataset_id')}",
            )
        )

    for position, case_baseline in enumerate(baseline.get("cases", [])):
        case_errors: list[dict[str, str]] = []
        prefix = f"baseline-scenarios.json.cases[{position}]"
        case_code = case_baseline.get("case_code")
        seen_codes.add(str(case_code))
        try:
            bundle = load_case_bundle(str(case_code), dataset_root)
        except KeyError as exc:
            case_errors.append(_issue("baseline_case_unknown", f"{prefix}.case_code", str(exc)))
            results.append({"case_code": case_code, "valid": False, "errors": case_errors})
            all_errors.extend(case_errors)
            continue

        actor_ids = {item.get("id") for item in bundle.get("actors", [])}
        event_ids = {item.get("id") for item in bundle.get("events", [])}
        fact_ids = {item.get("id") for item in bundle.get("facts", [])}
        evidence_ids = {item.get("id") for item in bundle.get("evidence", [])}
        facts_by_id = {item.get("id"): item for item in bundle.get("facts", [])}
        documents_by_id = {item.get("id"): item for item in bundle.get("documents", [])}

        if case_baseline.get("dataset_case_id") != bundle.get("case_code"):
            case_errors.append(
                _issue(
                    "baseline_dataset_case_id_mismatch",
                    f"{prefix}.dataset_case_id",
                    f"expected {bundle.get('case_code')}, got {case_baseline.get('dataset_case_id')}",
                )
            )
        if case_baseline.get("t3_bundle_id") != bundle.get("case_id"):
            case_errors.append(
                _issue(
                    "baseline_bundle_id_mismatch",
                    f"{prefix}.t3_bundle_id",
                    f"expected {bundle.get('case_id')}, got {case_baseline.get('t3_bundle_id')}",
                )
            )

        actual_counts = {
            "actors": len(actor_ids),
            "events": len(event_ids),
            "facts": len(fact_ids),
            "evidence": len(evidence_ids),
            "relationships": len(bundle.get("relationships", [])),
        }
        if case_baseline.get("entity_counts") != actual_counts:
            case_errors.append(
                _issue(
                    "baseline_entity_counts_mismatch",
                    f"{prefix}.entity_counts",
                    f"expected {actual_counts}, got {case_baseline.get('entity_counts')}",
                )
            )

        for evidence_position, evidence in enumerate(bundle.get("evidence", [])):
            document = documents_by_id.get(evidence.get("document_id"), {})
            if document.get("role") != "case_material":
                case_errors.append(
                    _issue(
                        "baseline_evidence_not_case_material",
                        f"{prefix}.bundle.evidence[{evidence_position}].document_id",
                        str(evidence.get("document_id")),
                    )
                )
        for fact_position, fact in enumerate(bundle.get("facts", [])):
            if not fact.get("evidence_ids"):
                case_errors.append(
                    _issue(
                        "baseline_fact_evidence_missing",
                        f"{prefix}.bundle.facts[{fact_position}].evidence_ids",
                        str(fact.get("id")),
                    )
                )

        source_bindings = case_baseline.get("source_bindings", [])
        binding_ids = {item.get("source_id") for item in source_bindings}
        bundle_source_ids = set(bundle.get("legal_source_ids", []))
        if binding_ids != bundle_source_ids:
            case_errors.append(
                _issue(
                    "baseline_source_coverage_mismatch",
                    f"{prefix}.source_bindings",
                    f"missing={sorted(bundle_source_ids - binding_ids)}, extra={sorted(binding_ids - bundle_source_ids)}",
                )
            )
        for binding_position, binding in enumerate(source_bindings):
            binding_path = f"{prefix}.source_bindings[{binding_position}]"
            source = sources_by_id.get(binding.get("source_id"))
            if source is None:
                case_errors.append(_issue("baseline_source_unknown", f"{binding_path}.source_id", str(binding.get("source_id"))))
                continue
            for field in ("effective_from", "effective_to", "signoff_status"):
                if binding.get(field) != source.get(field):
                    case_errors.append(
                        _issue(
                            "baseline_source_metadata_mismatch",
                            f"{binding_path}.{field}",
                            f"catalog={source.get(field)}, binding={binding.get(field)}",
                        )
                    )
            if binding.get("signoff_status") != "pending" or binding.get("public_eligible") is not False:
                case_errors.append(
                    _issue(
                        "baseline_source_not_fail_closed",
                        binding_path,
                        "unsigned sources must remain pending and public_eligible=false",
                    )
                )
            use_scope = binding.get("use_scope")
            applicable_to_conduct = binding.get("applicable_to_conduct")
            if use_scope in {"sentencing_reference", "current_review_audit_only"} and applicable_to_conduct is not False:
                case_errors.append(
                    _issue(
                        "baseline_temporal_scope_unsafe",
                        f"{binding_path}.applicable_to_conduct",
                        f"{use_scope} must not be promoted to a conduct-time source",
                    )
                )

        scenarios = case_baseline.get("scenarios", [])
        path_kinds = {item.get("path_kind") for item in scenarios}
        if "normal" not in path_kinds or not path_kinds.intersection({"missing_evidence", "conflicted_fact"}):
            case_errors.append(
                _issue(
                    "baseline_scenario_pair_incomplete",
                    f"{prefix}.scenarios",
                    "one normal path and one missing-evidence/conflicted-fact path are required",
                )
            )
        for scenario_position, scenario in enumerate(scenarios):
            scenario_path = f"{prefix}.scenarios[{scenario_position}]"
            if scenario.get("actor_id") not in actor_ids:
                case_errors.append(_issue("baseline_actor_unknown", f"{scenario_path}.actor_id", str(scenario.get("actor_id"))))
            expected = scenario.get("expected") or {}
            mutations = scenario.get("mutations", [])
            if scenario.get("path_kind") == "normal":
                if mutations or expected.get("module_status") != "waiting_review" or expected.get("blockers"):
                    case_errors.append(
                        _issue(
                            "baseline_normal_path_invalid",
                            scenario_path,
                            "normal path must be unmodified, waiting_review, and blocker-free",
                        )
                    )
            else:
                if expected.get("module_status") != "blocked" or not expected.get("blockers"):
                    case_errors.append(
                        _issue(
                            "baseline_blocked_path_invalid",
                            scenario_path,
                            "negative path must be blocked and name at least one blocker",
                        )
                    )
            for mutation_position, mutation in enumerate(mutations):
                mutation_path = f"{scenario_path}.mutations[{mutation_position}]"
                fact = facts_by_id.get(mutation.get("fact_id"))
                if fact is None:
                    case_errors.append(_issue("baseline_fact_unknown", f"{mutation_path}.fact_id", str(mutation.get("fact_id"))))
                    continue
                if mutation.get("operation") == "remove_evidence":
                    evidence_id = mutation.get("evidence_id")
                    if evidence_id not in evidence_ids or evidence_id not in set(fact.get("evidence_ids", [])):
                        case_errors.append(
                            _issue(
                                "baseline_evidence_mutation_invalid",
                                f"{mutation_path}.evidence_id",
                                f"{evidence_id} is not evidence for {fact.get('id')}",
                            )
                        )
                elif mutation.get("operation") == "use_conflicted_fact" and fact.get("verification_status") != "conflicted":
                    case_errors.append(
                        _issue(
                            "baseline_conflict_mutation_invalid",
                            f"{mutation_path}.fact_id",
                            f"{fact.get('id')} is {fact.get('verification_status')}, not conflicted",
                        )
                    )

        mapping = case_baseline.get("t1_mapping") or {}
        if mapping.get("datasetCaseId") != bundle.get("case_code") or mapping.get("t3BundleId") != bundle.get("case_id"):
            case_errors.append(
                _issue(
                    "baseline_t1_identity_mapping_invalid",
                    f"{prefix}.t1_mapping",
                    "datasetCaseId/t3BundleId must map to bundle.case_code/bundle.case_id",
                )
            )
        required_trace_fields = {"datasetCaseId", "t3BundleId", "factsVersion", "sourceVersion"}
        if set(mapping.get("requiredResultFields", [])) != required_trace_fields:
            case_errors.append(
                _issue(
                    "baseline_t1_trace_fields_incomplete",
                    f"{prefix}.t1_mapping.requiredResultFields",
                    ", ".join(sorted(required_trace_fields)),
                )
            )

        result = {
            "case_code": case_code,
            "case_id": bundle.get("case_id"),
            "valid": not case_errors,
            "errors": case_errors,
            "entity_counts": actual_counts,
            "source_count": len(source_bindings),
            "scenario_count": len(scenarios),
        }
        results.append(result)
        all_errors.extend(case_errors)

    if seen_codes != {"A", "B", "C"}:
        all_errors.append(
            _issue(
                "baseline_case_set_incomplete",
                "baseline-scenarios.json.cases",
                f"expected A/B/C, got {sorted(seen_codes)}",
            )
        )

    return {
        "valid": not all_errors,
        "schema_version": baseline.get("schema_version"),
        "dataset_id": baseline.get("dataset_id"),
        "revision": baseline.get("revision"),
        "public_release": baseline.get("public_release"),
        "errors": all_errors,
        "cases": results,
    }


def validate_case_dataset(root: Path | None = None) -> dict[str, Any]:
    """Validate the formal JSON shape and all cross-record references before import."""

    dataset_root = root or DEMO_ROOT
    index = load_case_dataset_index(dataset_root)
    index_schema_errors = _schema_issues(index, INDEX_SCHEMA_PATH)
    safe_index = index if isinstance(index, dict) else {}
    template_registry = load_document_template_registry(dataset_root)
    template_validation = validate_document_template_registry(template_registry)
    baseline_validation = validate_three_case_baseline(dataset_root)
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = list(index_schema_errors)
    seen_ids: set[str] = set()
    seen_codes: set[str] = set()
    seen_external_ids: set[str] = set()
    cases = safe_index.get("cases", [])
    if not isinstance(cases, list):
        cases = []
    for position, item in enumerate(cases):
        if not isinstance(item, dict):
            continue
        case_id = item.get("case_id")
        case_code = item.get("case_code")
        external_case_id = item.get("external_case_id")
        if case_id in seen_ids or case_code in seen_codes or external_case_id in seen_external_ids:
            errors.append(
                _issue(
                    "duplicate_case",
                    f"cases[{position}]",
                    f"duplicate case identity: {case_id}/{case_code}/{external_case_id}",
                )
            )
            continue
        seen_ids.add(case_id)
        seen_codes.add(case_code)
        seen_external_ids.add(external_case_id)
        bundle_path = dataset_root / str(item.get("bundle", ""))
        if not bundle_path.is_file():
            errors.append(_issue("bundle_missing", f"cases[{position}].bundle", str(bundle_path)))
            continue
        bundle = _read_json(bundle_path)
        bundle_schema_errors = _schema_issues(bundle, BUNDLE_SCHEMA_PATH, str(item.get("bundle", "bundle")))
        if bundle.get("case_id") != case_id or bundle.get("case_code") != case_code:
            errors.append(_issue("index_identity_mismatch", f"cases[{position}]", str(bundle_path)))
        semantic = validate_case_bundle(bundle, template_registry=template_registry)
        semantic["external_case_id"] = external_case_id
        semantic["schema_errors"] = bundle_schema_errors
        semantic["errors"] = bundle_schema_errors + semantic["errors"]
        semantic["valid"] = not semantic["errors"]
        results.append(semantic)
    return {
        "valid": (
            not errors
            and template_validation["valid"]
            and baseline_validation["valid"]
            and len(results) == 3
            and all(item["valid"] for item in results)
        ),
        "schema_version": safe_index.get("schema_version"),
        "producer_id": safe_index.get("producer_id"),
        "dataset_id": safe_index.get("dataset_id"),
        "revision": safe_index.get("revision"),
        "errors": errors + template_validation["errors"] + baseline_validation["errors"],
        "cases": results,
        "document_templates": template_validation,
        "baseline_scenarios": baseline_validation,
        "expected_case_count": 3,
        "actual_case_count": len(results),
    }
