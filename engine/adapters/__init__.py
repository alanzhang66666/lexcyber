"""Internal, fail-closed adapters used by the three-case legal demo."""

from engine.adapters.case_bundle import (
    load_case_bundle,
    load_document_template_registry,
    load_three_case_baseline,
    validate_case_bundle,
    validate_case_dataset,
    validate_document_template_registry,
    validate_three_case_baseline,
)
from engine.adapters.consistency import validate_result_consistency
from engine.adapters.sentencing import calculate_case_sentencing, calculate_sentencing
from engine.adapters.sources import get_legal_source, search_legal_sources
from engine.adapters.t1_contract import (
    T1ContractError,
    build_t1_case_create,
    build_t1_fact_view,
    build_t1_module_state,
    map_sentencing_result_to_t1,
)

__all__ = [
    "calculate_case_sentencing",
    "calculate_sentencing",
    "build_t1_case_create",
    "build_t1_fact_view",
    "build_t1_module_state",
    "get_legal_source",
    "load_case_bundle",
    "load_document_template_registry",
    "load_three_case_baseline",
    "search_legal_sources",
    "map_sentencing_result_to_t1",
    "T1ContractError",
    "validate_case_bundle",
    "validate_case_dataset",
    "validate_document_template_registry",
    "validate_three_case_baseline",
    "validate_result_consistency",
]
