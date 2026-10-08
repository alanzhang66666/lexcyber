from __future__ import annotations

import pytest

from engine.rules import registry


def _no_connection():
    raise AssertionError("invalid initial review status must fail before opening a connection")


@pytest.mark.parametrize("status", ["approved", "rejected", "superseded"])
def test_rule_initial_review_statuses_are_pending_only(monkeypatch, status):
    monkeypatch.setattr(registry, "connection", _no_connection)
    with pytest.raises(registry.RegistryError) as err:
        registry.register_rule_package({"legal_review_status": status})
    assert err.value.code == "REGISTRY_REVIEW_REQUIRED"


@pytest.mark.parametrize("status", ["approved", "rejected", "superseded"])
def test_template_initial_review_statuses_are_pending_only(monkeypatch, status):
    monkeypatch.setattr(registry, "connection", _no_connection)
    with pytest.raises(registry.RegistryError) as err:
        registry.register_template({"legal_review_status": status})
    assert err.value.code == "REGISTRY_REVIEW_REQUIRED"


@pytest.mark.parametrize("status", ["signed_off", "disputed", "unsupported"])
def test_source_initial_review_statuses_require_signoff(monkeypatch, status):
    monkeypatch.setattr(registry, "connection", _no_connection)
    with pytest.raises(registry.RegistryError) as err:
        registry.register_legal_source({"verification_level": status})
    assert err.value.code == "REGISTRY_REVIEW_REQUIRED"
