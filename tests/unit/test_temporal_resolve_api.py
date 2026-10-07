from datetime import date

import pytest
from fastapi.testclient import TestClient

from engine.api import app
from engine.rules import registry
from engine.settings import settings


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "service_token", "temporal-test-token")
    return TestClient(app)


@pytest.mark.parametrize("field,value", [
    ("conductDate", "2026-02-30"),
    ("judgmentDate", "2026-1-1"),
    ("conductDate", "2026-01-01T00:00:00Z"),
    ("judgmentDate", ""),
    ("conductDate", ["2026-01-01"]),
])
def test_invalid_date_returns_400_without_querying_registry(client, monkeypatch, field, value):
    monkeypatch.setattr(registry, "resolve_temporal", lambda *args: pytest.fail("invalid dates must not query"))

    response = client.post("/internal/v1/registry/resolve",
                           headers={"X-Service-Token": "temporal-test-token"},
                           json={"sourceKey": "source", field: value})

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_AS_OF_DATE"


def test_confirmed_request_passes_explicit_dates_to_registry(client, monkeypatch):
    calls = []

    def resolve(*args):
        calls.append(args)
        return {"found": True, "divergence": []}

    monkeypatch.setattr(registry, "resolve_temporal", resolve)
    response = client.post("/internal/v1/registry/resolve",
                           headers={"X-Service-Token": "temporal-test-token"},
                           json={"sourceKey": "source", "conductDate": "2024-01-01", "judgmentDate": "2026-01-01"})

    assert response.status_code == 200
    assert calls == [("source", date(2024, 1, 1), date(2026, 1, 1))]


def test_registry_resolution_still_requires_service_authentication(client, monkeypatch):
    monkeypatch.setattr(registry, "resolve_temporal", lambda *args: pytest.fail("authentication must precede query"))
    response = client.post("/internal/v1/registry/resolve", json={"sourceKey": "source"})
    assert response.status_code == 401


@pytest.mark.parametrize("source_key", [None, "", [], 1])
def test_invalid_source_key_returns_400(client, source_key):
    response = client.post("/internal/v1/registry/resolve",
                           headers={"X-Service-Token": "temporal-test-token"},
                           json={"sourceKey": source_key})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_SOURCE_KEY"
