"""draft.render 渲染器单测（registry 打桩）。"""
from __future__ import annotations

import pytest

from engine.adapters import document_render
from engine.adapters.document_render import render
from engine.adapters.module_analysis import ModuleAnalysisError

TEMPLATE = {
    "templatePackageId": "tp-1", "templateId": "indictment", "templateVersion": "1.0.0",
    "fieldSchema": {"required": ["facts.defendant_name.value"]},
    "bodyTemplate": "被告人{{facts.defendant_name.value}}，涉案金额{{amounts.inflow.confirmedSum}}元，"
                    "定罪状态{{artifacts.conviction.status}}。",
    "contentHash": "th1",
}

SNAPSHOT = {
    "items": [{"key": "defendant_name", "entityId": "fact-defendant", "value": "张某", "verificationStatus": "confirmed", "evidenceIds": ["proof-1"]}],
    "entities": {"amounts": [{"kind": "inflow", "value": "250000", "entityId": "amount-1", "evidenceIds": ["proof-1"],
                              "verificationStatus": "confirmed"}],
                  "evidence": [{"entityId": "proof-1", "verificationStatus": "confirmed"}]},
}


def _payload(artifacts=None):
    return {"case_id": "c1", "input_snapshot_ref": "facts_version:fv-3",
            "metadata": {"taskType": "draft.render", "asOfDate": "2026-01-01", "docType": "indictment",
                         "factsSnapshot": SNAPSHOT,
                         "artifactVersions": {"conviction": "11111111-1111-1111-1111-111111111111"},
                         "artifacts": artifacts or {"conviction": {"schema_version": "case.conviction.v2", "status": "calculated",
                            "input_validation": {"schema_version": "case.input-validation.v1", "status": "verified", "checks": [], "blockers": []}}}}
    }


def test_rendered(monkeypatch):
    monkeypatch.setattr(document_render.registry, "active_template", lambda dt: TEMPLATE)
    out = render(_payload())
    body = out["final_output"]
    assert body["status"] == "rendered"
    assert "被告人张某" in body["body"]
    assert "250000" in body["body"]
    assert "calculated" in body["body"]
    assert body["template"]["contentHash"] == "th1"
    assert body["dependency_snapshot"]["facts_version_id"] == "fv-3"
    assert body["human_review_required"] is True
    assert body["dependency_snapshot"]["artifacts"] == [
        {"module": "conviction", "artifactVersionId": "11111111-1111-1111-1111-111111111111"}]


def test_missing_input_version_fails_closed(monkeypatch):
    monkeypatch.setattr(document_render.registry, "active_template", lambda dt: TEMPLATE)
    payload = _payload()
    del payload["metadata"]["artifactVersions"]
    with pytest.raises(ModuleAnalysisError) as err:
        render(payload)
    assert err.value.code == "ARTIFACT_SNAPSHOT_MISSING"


def test_blocked_upstream_never_produces_body(monkeypatch):
    monkeypatch.setattr(document_render.registry, "active_template", lambda dt: TEMPLATE)
    body = render(_payload({"conviction": {"status": "blocked"}}))["final_output"]
    assert body["status"] == "blocked"
    assert body["body"] is None
    assert {"path": "artifacts.conviction", "reason": "upstream_blocked"} in body["unresolved"]


def test_unresolved_blocks_no_body(monkeypatch):
    monkeypatch.setattr(document_render.registry, "active_template", lambda dt: TEMPLATE)
    snap = {"items": [], "entities": {}}  # 缺 defendant_name
    payload = _payload()
    payload["metadata"]["factsSnapshot"] = snap
    out = render(payload)
    body = out["final_output"]
    assert body["status"] == "blocked"
    assert body["body"] is None
    paths = {u["path"] for u in body["unresolved"]}
    assert "facts.defendant_name.value" in paths


def test_no_template_fails_closed(monkeypatch):
    monkeypatch.setattr(document_render.registry, "active_template", lambda dt: None)
    with pytest.raises(ModuleAnalysisError) as err:
        render(_payload())
    assert err.value.code == "TEMPLATE_UNAVAILABLE"


def test_missing_doc_type():
    payload = _payload()
    payload["metadata"] = {"taskType": "draft.render", "asOfDate": "2026-01-01", "factsSnapshot": SNAPSHOT}
    with pytest.raises(ModuleAnalysisError) as err:
        render(payload)
    assert err.value.code == "DOC_TYPE_MISSING"


def test_missing_as_of_date_fails_closed(monkeypatch):
    monkeypatch.setattr(document_render.registry, "active_template", lambda dt: TEMPLATE)
    payload = _payload()
    del payload["metadata"]["asOfDate"]
    with pytest.raises(ModuleAnalysisError) as err:
        render(payload)
    assert err.value.code == "INVALID_AS_OF_DATE"


def test_chinese_placeholder_in_template_blocks_body(monkeypatch):
    template = dict(TEMPLATE, bodyTemplate="被告人{{facts.defendant_name.value}}【待核实】")
    monkeypatch.setattr(document_render.registry, "active_template", lambda dt: template)
    out = render(_payload())["final_output"]
    assert out["status"] == "blocked"
    assert out["body"] is None
    assert {"path": "body", "reason": "unresolved_placeholder"} in out["unresolved"]


def test_chinese_placeholder_introduced_by_fact_blocks_body(monkeypatch):
    monkeypatch.setattr(document_render.registry, "active_template", lambda dt: TEMPLATE)
    payload = _payload()
    payload["metadata"]["factsSnapshot"] = {
        "items": [{"key": "defendant_name", "value": "张【待补充】", "verificationStatus": "confirmed"}],
        "entities": {"amounts": [{"kind": "inflow", "value": "250000", "verificationStatus": "confirmed"}]},
    }
    out = render(payload)["final_output"]
    assert out["status"] == "blocked"
    assert out["body"] is None
    assert {"path": "body", "reason": "unresolved_placeholder"} in out["unresolved"]


def test_invalid_upstream_marker_blocks_render(monkeypatch):
    monkeypatch.setattr(document_render.registry, "active_template", lambda dt: TEMPLATE)
    payload = _payload({"conviction": {
        "schema_version": "case.conviction.v2", "status": "calculated",
        "input_validation": {"schema_version": "case.input-validation.v1",
                              "status": "verified", "checks": [{}], "blockers": []}}})
    body = render(payload)["final_output"]
    assert body["status"] == "blocked"
    assert body["body"] is None
    assert any(item["reason"] == "upstream_input_validation_blocked"
               for item in body["unresolved"])
