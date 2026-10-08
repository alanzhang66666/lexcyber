from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

import engine.api as api
import engine.store as store
from engine.rules.dependency_validity import (
    GLOBAL_BARRIER_KEY,
    validate_dependency_request,
    verify_coordination,
)
from engine.settings import settings


def test_dependency_request_is_strict_and_uuid_checked():
    parsed, errors = validate_dependency_request({
        "coordination": {"backendPid": 12, "challenge": "99"},
        "dependencies": [{"kind": "legal_source", "key": "bad", "version": "1"}],
    })
    assert parsed is not None
    assert not errors


def test_malformed_dependency_shapes_are_controlled():
    parsed, errors = validate_dependency_request({"coordination": {}, "dependencies": [None]})
    assert parsed is None
    assert errors[0]["code"] == "INVALID_REGISTRY_DEPENDENCIES"


def test_coordination_rejects_global_or_unproven_advisory_lock():
    class Cursor:
        def execute(self, *_args):
            return self
        def fetchone(self):
            return None
    assert not verify_coordination(Cursor(), 12, str(GLOBAL_BARRIER_KEY))
    assert not verify_coordination(Cursor(), 12, "99")


@pytest.fixture
def registry_http(monkeypatch):
    monkeypatch.setattr(settings, "service_token", "registry-unit-token")
    return TestClient(api.app), {"X-Service-Token": "registry-unit-token"}


def request_body():
    return {"coordination": {"backendPid": 12, "challenge": "99"},
            "dependencies": [{"kind": "rule", "key": "frozen", "version": "1"}]}


@pytest.mark.parametrize("payload", [None, [], "body", True, 10, {},
    {"coordination": {"backendPid": True, "challenge": "99"}, "dependencies": []},
    {"coordination": {"backendPid": 12, "challenge": str(1 << 63)}, "dependencies": []},
    {"coordination": {"backendPid": 12, "challenge": str(GLOBAL_BARRIER_KEY)}, "dependencies": []},
    *[{"coordination": {"backendPid": 12, "challenge": "99"},
       "dependencies": [{"kind": kind, "key": "frozen", "version": "1"}]}
      for kind in ([], {}, True, None)],
])
def test_http_malformed_json_has_controlled_400(registry_http, payload):
    import json
    client, headers = registry_http
    response = client.post("/internal/v1/registry/verify-dependencies", headers=headers,
                           content=json.dumps(payload))
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_REGISTRY_DEPENDENCIES"


def test_registry_http_authentication_is_required(registry_http):
    client, _ = registry_http
    assert client.post("/internal/v1/registry/verify-dependencies", json=request_body()).status_code == 401


def test_registry_http_unproven_coordination_is_409(registry_http, monkeypatch):
    client, headers = registry_http
    @contextmanager
    def fake_connection():
        yield object()
    monkeypatch.setattr(store, "connection", fake_connection)
    monkeypatch.setattr(api, "verify_coordination", lambda *args: False)
    response = client.post("/internal/v1/registry/verify-dependencies", headers=headers, json=request_body())
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "REGISTRY_COORDINATION_REQUIRED"


def test_registry_http_database_failure_is_503_not_missing_dependency(registry_http, monkeypatch):
    client, headers = registry_http
    @contextmanager
    def failed_connection():
        raise RuntimeError("database unavailable")
        yield
    monkeypatch.setattr(store, "connection", failed_connection)
    response = client.post("/internal/v1/registry/verify-dependencies", headers=headers, json=request_body())
    assert response.status_code == 503


def test_registry_http_exact_empty_version_is_invalid_without_guessing_latest(registry_http, monkeypatch):
    client, headers = registry_http
    class MissingVersionConnection:
        def execute(self, sql, params):
            assert params == ("frozen", "")
            assert "rule_version = %s" in sql
            return self
        def fetchone(self):
            return None
    @contextmanager
    def fake_connection():
        yield MissingVersionConnection()
    monkeypatch.setattr(store, "connection", fake_connection)
    monkeypatch.setattr(api, "verify_coordination", lambda *args: True)
    body = request_body()
    body["dependencies"][0]["version"] = ""
    response = client.post("/internal/v1/registry/verify-dependencies", headers=headers, json=body)
    assert response.status_code == 200
    result = response.json()
    assert result["valid"] is False
    assert result["invalidDependencies"][0]["version"] == ""
