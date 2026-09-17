import pytest

from engine.adapters.case_bundle import load_case_bundle, validate_case_bundle, validate_case_dataset
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


def test_benchmark_annotation_does_not_count_as_case_evidence():
    bundle = load_case_bundle("A")
    result = validate_case_bundle(bundle)
    warning_codes = {item["code"] for item in result["warnings"]}
    case_material_ids = {item["id"] for item in bundle["documents"] if item["role"] == "case_material"}
    assert {item["document_id"] for item in bundle["evidence"]} <= case_material_ids
    assert "sentencing_not_approved" in warning_codes


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


def test_case_sentencing_is_blocked_until_legal_approval():
    bundle = load_case_bundle("B")
    result = calculate_case_sentencing(bundle, "actor-b-huang")
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
        {"case_name": "【待补充】"},
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
    assert payload["asOfDate"] == "2026-09-17"
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
            bundle,
            case_id="case-server-a",
            document_id_map={"doc-a-input": "doc-server-a"},
            status="confirmed",
            item_ids=["fact-a-payment-settlement-classification"],
        )


def test_t1_mapping_keeps_blocked_inside_content_and_uses_waiting_review_task_status():
    result = calculate_case_sentencing(load_case_bundle("B"), "actor-b-huang")
    payload = map_sentencing_result_to_t1(result, case_id="case-server-b", dataset_case_id="B")
    assert payload["taskStatus"] == "waiting_review"
    assert payload["content"]["analysisStatus"] == "blocked"
    assert payload["content"]["caseId"] == "case-server-b"
    assert payload["content"]["datasetCaseId"] == "B"
    assert payload["content"]["t3BundleId"] == "demo-case-b-proceeds"
    assert "status" not in payload["content"]
