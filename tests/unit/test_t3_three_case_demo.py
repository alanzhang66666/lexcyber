import pytest

from engine.adapters.case_bundle import (
    load_case_bundle,
    load_document_template_registry,
    validate_case_bundle,
    validate_case_dataset,
    validate_document_template_registry,
)
from engine.adapters.consistency import validate_result_consistency
from engine.adapters.sentencing import calculate_case_sentencing, calculate_sentencing
from engine.adapters.sources import search_legal_sources
from engine.adapters.t1_contract import (
    T1ContractError,
    build_t1_case_create,
    build_t1_fact_view,
    build_t1_module_state,
    map_sentencing_result_to_t1,
)
from skills.legal.case.fact_extract import execute as extract_facts


def test_three_case_dataset_has_stable_valid_bundles():
    result = validate_case_dataset()
    assert result["valid"] is True
    assert result["actual_case_count"] == 3
    assert {item["case_id"] for item in result["cases"]} == {
        "demo-case-a-helping",
        "demo-case-b-proceeds",
        "demo-case-c-unit-crossborder",
    }
    assert all(item["counts"]["evidence"] >= 8 for item in result["cases"])
    assert result["document_templates"] == {"valid": True, "errors": [], "template_count": 3}


def test_document_templates_are_versioned_and_referenced_by_each_case():
    registry = load_document_template_registry()
    assert validate_document_template_registry(registry)["valid"] is True
    templates = {item["id"]: item for item in registry["templates"]}
    assert {item["document_type"] for item in templates.values()} == {
        "prosecution",
        "sentencing_recommendation",
        "non_prosecution",
    }
    assert all(len(item["sha256"]) == 64 for item in templates.values())
    assert all(item["mapping_status"] != "approved" for item in templates.values())

    for case_code in ("A", "B", "C"):
        bundle = load_case_bundle(case_code)
        document_fields = bundle["document_fields"]
        assert document_fields["template_structure_status"] == "source_registered"
        assert set(document_fields["template_ids"]) <= set(templates)
        assert document_fields["template_legal_review_status"] != "approved"


def test_benchmark_annotation_does_not_count_as_case_evidence():
    bundle = load_case_bundle("A")
    result = validate_case_bundle(bundle)
    warning_codes = {item["code"] for item in result["warnings"]}
    case_material_ids = {item["id"] for item in bundle["documents"] if item["role"] == "case_material"}
    assert {item["document_id"] for item in bundle["evidence"]} <= case_material_ids
    assert "sentencing_not_approved" not in warning_codes


def test_case_b_includes_case_042_and_keeps_original_and_adapted_outcomes_distinct():
    bundle = load_case_bundle("B")
    documents = {item["id"]: item for item in bundle["documents"]}
    assert documents["doc-b-042-input"]["role"] == "case_material"
    assert documents["doc-b-042-input"]["archive_entry"].endswith(".docx")
    assert documents["doc-b-042-input"]["original_archive_entry"].endswith(".doc")
    assert documents["doc-b-042-input"]["conversion"]["content_match"] is True
    assert documents["doc-b-042-benchmark"]["role"] == "benchmark_annotation"

    facts = {item["id"]: item for item in bundle["facts"]}
    assert facts["fact-b-042-proceeds-formed"]["verification_status"] == "confirmed"
    assert facts["fact-b-042-knowledge"]["verification_status"] == "conflicted"

    paths = {item["id"]: item for item in bundle["analyses"]["conviction"]["candidate_paths"]}
    assert paths["path-b-chen-concealment"]["baseline_position"] == "adapted_benchmark_selected_not_actual_judgment"
    assert paths["path-b-chen-helping"]["baseline_position"] == "original_source_outcome_not_selected_in_adaptation"

    chen = next(item for item in bundle["sentencing"]["actor_baselines"] if item["actor_id"] == "actor-b-chen")
    assert chen["benchmark_disposition"]["nature"] == "adapted_legal_reviewed_declared_disposition_replayed_not_actual_judgment"
    assert chen["original_source_disposition"]["offence"] == "帮助信息网络犯罪活动罪"
    assert "missing-b-01" not in {item["id"] for item in bundle["missing_items"]}


def test_round3_review_summary_is_registered_for_all_cases():
    expected_hash = "b1b3c027e11f939cb6bb7541d50bfb7d6460de07a5d45fc1e0cc822c2c49a9d9"
    for case_code in ("A", "B", "C"):
        bundle = load_case_bundle(case_code)
        review_summary_id = f"doc-{case_code.lower()}-review-summary-round3"
        documents = {item["id"]: item for item in bundle["documents"]}
        assert bundle["legal_review"]["review_summary"] == review_summary_id
        assert review_summary_id in bundle["legal_review"]["reviewed_sources"]
        assert documents[review_summary_id]["sha256"] == expected_hash
        assert documents[review_summary_id]["role"] == "legal_review_summary"


def test_case_a_reviewed_amount_classifications_are_resolved():
    bundle = load_case_bundle("A")
    facts = {item["id"]: item for item in bundle["facts"]}
    amounts = {item["id"]: item for item in bundle["amounts"]}
    assert facts["fact-a-payment-settlement-classification"]["verification_status"] == "confirmed"
    assert amounts["amount-a-equipment-revenue"]["kind"] == "non_crime_flow"
    assert amounts["amount-a-personal-profit"]["kind"] == "personal_profit"
    assert amounts["amount-a-upstream-loss"]["kind"] == "crime_amount"
    assert "missing-a-01" not in {item["id"] for item in bundle["missing_items"]}


def test_case_b_009_reviewed_range_is_replayed_without_synthetic_arithmetic():
    bundle = load_case_bundle("B")
    baseline = next(item for item in bundle["sentencing"]["actor_baselines"] if item["actor_id"] == "actor-b-huang")
    disposition = baseline["benchmark_disposition"]
    assert baseline["legal_review_status"] == "approved"
    assert disposition["term_range_months"] == [4, 8]
    assert disposition["term_lower_kind"] == "detention"
    assert disposition["term_upper_kind"] == "fixed_term_imprisonment"
    assert disposition["fine_range_cny"] == [3000, 10000]
    assert "missing-b-02" not in {item["id"] for item in bundle["missing_items"]}

    result = calculate_case_sentencing(bundle, "actor-b-huang")
    assert result["status"] == "calculated"
    assert result["calculation_mode"] == "reviewed_disposition_replay"
    assert result["term_range_months"] == [4, 8]
    assert result["fine_range_cny"] == [3000, 10000]
    assert result["blockers"] == []
    declared = result["reviewed_rule_outline"]["declared_disposition"]
    assert declared["term_range_months"] == disposition["term_range_months"]
    assert declared["fine_range_cny"] == disposition["fine_range_cny"]


def test_section_six_reviewed_dispositions_are_registered_and_replayed():
    expected_actors = {
        "A": {"actor-a-feng"},
        "B": {"actor-b-huang", "actor-b-chen"},
        "C": {"actor-c-company", "actor-c-jia", "actor-c-yi"},
    }
    for case_code, actor_ids in expected_actors.items():
        bundle = load_case_bundle(case_code)
        baselines = {item["actor_id"]: item for item in bundle["sentencing"]["actor_baselines"]}
        assert set(baselines) == actor_ids
        for actor_id, baseline in baselines.items():
            rule = baseline["calculation_rule"]
            assert rule["rule_type"] == "reviewed_disposition"
            assert rule["rule_version"].startswith("review-summary-section-6-")
            assert rule["legal_review_status"] == "approved"
            assert rule["source_document_id"] == f"doc-{case_code.lower()}-review-summary-round3"
            assert rule["source_section"].startswith("六、各主体量刑规则")
            assert rule["declared_disposition"]
            assert "execution_blockers" not in rule

            result = calculate_case_sentencing(bundle, actor_id)
            assert result["status"] == "calculated"
            assert result["calculation_mode"] == "reviewed_disposition_replay"
            assert result["blockers"] == []
            assert result["reviewed_rule_outline"]["declared_disposition"] == rule["declared_disposition"]


def test_section_six_exact_and_fine_only_dispositions_are_supported():
    case_b = load_case_bundle("B")
    chen = calculate_case_sentencing(case_b, "actor-b-chen")
    assert chen["status"] == "calculated"
    assert chen["term_months"] == 27
    assert chen["fine"] == 10000
    assert chen["recovery_cny"] == 6409

    case_c = load_case_bundle("C")
    company = calculate_case_sentencing(case_c, "actor-c-company")
    assert company["status"] == "calculated"
    assert company["term_months"] is None
    assert company["fine_range_cny"] == [30000, 80000]


def test_case_c_reviewed_amounts_avoid_double_counting_and_jurisdiction_is_resolved():
    bundle = load_case_bundle("C")
    amounts = {item["id"]: item for item in bundle["amounts"]}
    assert amounts["amount-c-service-fee"]["value"] == 118000
    assert amounts["amount-c-service-fee"]["kind"] == "crime_proceeds"
    assert amounts["amount-c-company-receipt"]["value"] == 98000
    assert amounts["amount-c-company-receipt"]["included_in_amount_id"] == "amount-c-service-fee"
    assert amounts["amount-c-project-bonus"]["value"] == 20000
    assert amounts["amount-c-project-bonus"]["kind"] == "personal_profit"
    for baseline in bundle["sentencing"]["actor_baselines"]:
        assert "amount-c-service-fee" in baseline["amount_ids"]
        assert "amount-c-company-receipt" not in baseline["amount_ids"]
        assert "amount-c-project-bonus" not in baseline["amount_ids"]

    conviction = bundle["analyses"]["conviction"]
    assert conviction["jurisdiction_status"] == "confirmed_cn_criminal_jurisdiction_foreign_details_not_required"
    foreign_connections = [
        item
        for item in bundle["jurisdiction_connections"]
        if item["verification_status"] != "confirmed"
    ]
    assert len(foreign_connections) == 7
    assert all(
        item["verification_status"] == "not_required_for_cn_criminal_jurisdiction"
        for item in foreign_connections
    )
    missing_ids = {item["id"] for item in bundle["missing_items"]}
    assert "missing-c-01" not in missing_ids
    assert "missing-c-02" not in missing_ids


def test_source_search_is_version_and_date_aware():
    old = search_legal_sources("旧掩隐解释", as_of_date="2024-05-12")
    assert old["documents"][0]["id"] == "cn-concealment-interpretation-2015-2021"
    assert old["documents"][0]["effective_status"] == "effective"

    new_before_effective = search_legal_sources("2025掩隐解释", as_of_date="2024-05-12")
    assert new_before_effective["documents"][0]["id"] == "cn-concealment-interpretation-2025-1-12"
    assert new_before_effective["documents"][0]["effective_status"] == "not_yet_effective"

    new_current = search_legal_sources("2025掩隐解释", as_of_date="2026-09-14")
    assert new_current["documents"][0]["effective_status"] == "effective"

    guidance = search_legal_sources("2024量刑指导意见二", as_of_date="2024-07-01")
    assert guidance["documents"][0]["id"] == "cn-sentencing-guidance-2024-2"
    assert guidance["documents"][0]["effective_status"] == "effective"


def test_source_search_fails_clearly_outside_three_case_coverage():
    result = search_legal_sources("海商法共同海损")
    assert result["status"] == "unsupported_query"
    assert result["documents"] == []


def test_case_sentencing_still_fails_closed_for_an_unapproved_rule():
    result = calculate_sentencing(
        {
            "case_id": "test-unapproved",
            "actor_id": "actor-test",
            "parameters": [
                {"id": "amount", "value": 1, "verification_status": "confirmed", "evidence_ids": ["ev-test"]}
            ],
            "rule": {
                "rule_type": "reviewed_disposition",
                "rule_version": "pending-v1",
                "legal_review_status": "pending",
                "source_ids": ["source-test"],
                "declared_disposition": {"term_months": 1},
            },
        }
    )
    assert result["status"] == "blocked"
    assert result["term_months"] is None
    assert "rule_not_approved" in {item["code"] for item in result["blockers"]}


def test_approved_sentencing_rule_replays_transparent_arithmetic():
    result = calculate_sentencing(
        {
            "case_id": "test-approved",
            "actor_id": "actor-test",
            "parameters": [
                {
                    "id": "confirmed-crime-amount",
                    "value": 200000,
                    "verification_status": "confirmed",
                    "evidence_ids": ["ev-test"],
                }
            ],
            "rule": {
                "rule_version": "human-approved-test-v1",
                "legal_review_status": "approved",
                "source_ids": ["source-test"],
                "base_months": 18,
                "minimum_months": 0,
                "maximum_months": 36,
                "adjustments": [
                    {
                        "id": "increase-test",
                        "operation": "percent_of_base",
                        "direction": "increase",
                        "value": 0.1,
                        "legal_review_status": "approved",
                        "source_ids": ["source-test"],
                    },
                    {
                        "id": "decrease-test",
                        "operation": "fixed_months",
                        "direction": "decrease",
                        "value": 2,
                        "legal_review_status": "approved",
                        "source_ids": ["source-test"],
                    },
                ],
            },
        }
    )
    assert result["status"] == "calculated"
    assert result["term_months"] == 17.8
    assert [step["id"] for step in result["steps"]] == ["base", "increase-test", "decrease-test"]
    assert result["human_review_required"] is True


def test_sentencing_rejects_unconfirmed_parameters():
    result = calculate_sentencing(
        {
            "parameters": [{"id": "amount", "value": 1, "verification_status": "candidate", "evidence_ids": ["ev"]}],
            "rule": {
                "rule_version": "approved-v1",
                "legal_review_status": "approved",
                "source_ids": ["source"],
                "base_months": 1,
            },
        }
    )
    assert result["status"] == "blocked"
    assert "parameter_unconfirmed" in {item["code"] for item in result["blockers"]}


def test_result_consistency_reports_amount_source_and_draft_gaps():
    bundle = load_case_bundle("A")
    result = validate_result_consistency(
        bundle,
        {
            "source_ids": ["unknown-source"],
            "evidence_ids": ["ev-a-01"],
            "input_snapshot": {"amount-a-personal-profit": 999},
        },
        {"case_name": "【案件名称】"},
    )
    codes = {item["code"] for item in result["issues"]}
    assert result["status"] == "NEED_HUMAN"
    assert {"unknown_legal_source", "amount_mismatch", "draft_field_missing", "draft_placeholder_unresolved"} <= codes


def test_fact_extractor_normalizes_chinese_amounts_without_promoting_them_to_confirmed_facts():
    result = extract_facts(
        {
            "document_id": "doc-test",
            "text": "2024年5月12日账户总流入42万元，其中查明涉诈资金20万元，黄某个人获利4200元。",
        }
    )
    amounts = [item for item in result["facts"] if item["type"] == "amount"]
    assert [item["normalized_value"] for item in amounts] == [420000.0, 200000.0, 4200.0]
    assert [item["amount_kind"] for item in amounts] == ["account_total_flow", "fraud_related_inflow", "personal_profit"]
    assert all(item["verification_status"] == "candidate" for item in amounts)


def test_t1_case_create_keeps_server_case_id_unassigned_and_splits_organizations():
    payload = build_t1_case_create(load_case_bundle("C"))
    assert "caseId" not in payload
    assert payload["asOfDate"] == "2026-09-18"
    assert payload["metadata"]["datasetCaseId"] == "C"
    assert payload["metadata"]["t3BundleId"] == "demo-case-c-unit-crossborder"
    relations = payload["metadata"]["relations"]
    assert all(item["actorId"] != "actor-c-company" for item in relations["actors"])
    company = next(item for item in relations["organizations"] if item["actorId"] == "actor-c-company")
    assert company["organizationId"] == "org-c-company"
    assert relations["accounts"] == []
    assert relations["jurisdictionConnections"]
    assert payload["metadata"]["sourceVersionBinding"]["temporal_review_status"] == "partial_approval"
    assert "procedureStage" not in payload["metadata"]
    assert any(item.get("documentId") == "doc-pending-upload" for item in relations["events"])
    assert relations["links"]


def test_t1_case_create_projects_accounts_from_bundle_b():
    payload = build_t1_case_create(load_case_bundle("B"))
    accounts = payload["metadata"]["relations"]["accounts"]
    assert accounts
    company = next(item for item in accounts if item["accountId"] == "account-b-company-bank")
    assert company["organizationId"] == "org-b-company"
    assert "actor-b-company" in company["actorIds"]
    assert company["type"] == "company_bank_account"
    personal = next(item for item in accounts if item["accountId"] == "account-b-042-chen-bank")
    assert personal["actorIds"] == ["actor-b-chen"]


def test_t1_case_create_maps_case_b_comparison_events_to_their_own_documents():
    payload = build_t1_case_create(
        load_case_bundle("B"),
        {"doc-b-input": "doc-server-009", "doc-b-042-input": "doc-server-042"},
    )
    events = {item["eventId"]: item for item in payload["metadata"]["relations"]["events"]}
    assert events["event-b-02"]["documentId"] == "doc-server-009"
    assert events["event-b-042-02"]["documentId"] == "doc-server-042"
    assert events["event-b-042-02"]["locator"] == "paragraph:7"


def test_t1_case_create_uses_uploaded_document_ids_and_string_locators():
    payload = build_t1_case_create(load_case_bundle("A"), {"doc-a-input": "doc-server-a"})
    traced_events = [item for item in payload["metadata"]["relations"]["events"] if "documentId" in item]
    assert traced_events
    assert {item["documentId"] for item in traced_events} == {"doc-server-a"}
    assert all(isinstance(item["locator"], str) for item in traced_events)


def test_t1_fact_view_uses_server_ids_and_projects_item_verification_status():
    payload = build_t1_fact_view(
        load_case_bundle("B"),
        case_id="case-server-b",
        document_id_map={"doc-b-input": "doc-server-b"},
        item_ids=["fact-b-proceeds-formation", "amount-b-fraud-inflow"],
    )
    assert payload["caseId"] == "case-server-b"
    assert payload["status"] == "draft"
    assert {item["id"] for item in payload["items"]} == {"fact-b-proceeds-formation", "amount-b-fraud-inflow"}
    assert all(item["sourceDocumentId"] == "doc-server-b" for item in payload["items"])
    assert all(item["verificationStatus"] == "confirmed" for item in payload["items"])
    assert payload["status"] != "confirmed"


def test_t1_module_state_puts_analysis_block_in_opaque_content():
    payload = build_t1_module_state(load_case_bundle("C"), "compliance", "case-server-c")
    assert payload["caseId"] == "case-server-c"
    assert payload["version"] == 0
    assert payload["applicability"] == "applicable"
    assert payload["content"]["applicability"] == "applicable"
    assert payload["sourceVersion"]
    with pytest.raises(T1ContractError, match="server CaseView.id"):
        build_t1_module_state(load_case_bundle("C"), "conviction", "demo-case-c-unit-crossborder")


def test_t1_fact_confirmation_requires_explicit_human_confirmed_selection():
    bundle = load_case_bundle("A")
    with pytest.raises(T1ContractError, match="explicit item_ids"):
        build_t1_fact_view(bundle, case_id="case-server-a", document_id_map={"doc-a-input": "doc-server-a"}, status="confirmed")
    confirmed = build_t1_fact_view(
        bundle,
        case_id="case-server-a",
        document_id_map={"doc-a-input": "doc-server-a"},
        status="confirmed",
        item_ids=["fact-a-help"],
    )
    assert confirmed["status"] == "confirmed"
    with pytest.raises(T1ContractError, match="cannot confirm unconfirmed"):
        build_t1_fact_view(
            load_case_bundle("B"),
            case_id="case-server-b",
            document_id_map={"doc-b-042-input": "doc-server-b"},
            status="confirmed",
            item_ids=["fact-b-042-knowledge"],
        )


def test_t1_mapping_preserves_reviewed_range_and_uses_waiting_review_task_status():
    result = calculate_case_sentencing(load_case_bundle("B"), "actor-b-huang")
    payload = map_sentencing_result_to_t1(result, case_id="case-server-b", dataset_case_id="B")
    assert payload["taskStatus"] == "waiting_review"
    assert payload["content"]["analysisStatus"] == "calculated"
    assert payload["content"]["calculationMode"] == "reviewed_disposition_replay"
    assert payload["content"]["caseId"] == "case-server-b"
    assert payload["content"]["datasetCaseId"] == "B"
    assert payload["content"]["t3BundleId"] == "demo-case-b-proceeds"
    assert payload["content"]["reviewedRuleOutline"]["declared_disposition"]["term_range_months"] == [4, 8]
    assert payload["content"]["termRangeMonths"] == [4, 8]
    assert payload["content"]["fineRangeCny"] == [3000, 10000]
    assert payload["content"]["blockers"] == []
    assert "status" not in payload["content"]
