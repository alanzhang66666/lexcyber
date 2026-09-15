"""Internal, fail-closed adapters used by the three-case legal demo."""

from engine.adapters.case_bundle import load_case_bundle, validate_case_bundle, validate_case_dataset
from engine.adapters.consistency import validate_result_consistency
from engine.adapters.sentencing import calculate_case_sentencing, calculate_sentencing
from engine.adapters.sources import get_legal_source, search_legal_sources
from engine.adapters.t1_contract import T1ContractError, build_t1_case_create, build_t1_fact_view, map_sentencing_result_to_t1

__all__ = [
    "calculate_case_sentencing",
    "calculate_sentencing",
    "build_t1_case_create",
    "build_t1_fact_view",
    "get_legal_source",
    "load_case_bundle",
    "search_legal_sources",
    "map_sentencing_result_to_t1",
    "T1ContractError",
    "validate_case_bundle",
    "validate_case_dataset",
    "validate_result_consistency",
]
