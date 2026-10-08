import pytest
from fastapi import HTTPException

from engine.adapters.sentencing import SentencingUnavailable, calculate
from engine.adapters.sources import SourceSearchUnavailable
from engine.adapters.sources import search as search_sources
from engine.api import search_sources as search_endpoint
from engine.contracts import SourceSearchRequest


def test_sentencing_adapter_does_not_invent_ranges() -> None:
    with pytest.raises(SentencingUnavailable) as error:
        calculate({"query": "量刑", "metadata": {"taskType": "sentencing.calculate"}})
    assert error.value.code == "SENTENCING_UNAVAILABLE"


def test_sources_adapter_does_not_use_sample_corpus() -> None:
    with pytest.raises(SourceSearchUnavailable) as error:
        search_sources({"query": "民法典", "top_k": 5})
    assert error.value.code == "SOURCE_SEARCH_UNAVAILABLE"


def test_internal_search_endpoint_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("engine.api.settings.service_token", "token")
    with pytest.raises(HTTPException) as error:
        search_endpoint(SourceSearchRequest(query="民法典"))
    assert error.value.status_code == 501
    assert error.value.detail == "SOURCE_SEARCH_UNAVAILABLE"


@pytest.mark.parametrize("value", [None, "", "2024-1-1", "2024-02-30"])
def test_enabled_source_search_requires_explicit_date(monkeypatch, value):
    monkeypatch.setattr("engine.adapters.sources.settings.legal_source_search_enabled", True)
    with pytest.raises(HTTPException) as error:
        search_endpoint(SourceSearchRequest(query="刑法", as_of_date=value))
    assert error.value.status_code == 400
    assert error.value.detail["code"] == "INVALID_AS_OF_DATE"
