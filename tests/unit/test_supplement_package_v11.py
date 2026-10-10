"""Checks for the V1.1 supplement package that do not need a database."""
from __future__ import annotations

from engine.adapters import document_render
from engine.adapters.document_render import render
from engine.adapters.legal_temporal import _reconcile_version_groups


def _selection(disposition="prosecution"):
    return {"confirmed": True, "documentDisposition": disposition, "chargeBoundaryUnresolved": False}


def _payload(facts, template, disposition="prosecution"):
    items = [{"key": key, "entityId": f"fact-{key}", "value": value,
              "verificationStatus": "confirmed", "evidenceIds": ["proof-1"]}
             for key, value in facts.items()]
    return {
        "case_id": "c1",
        "input_snapshot_ref": "facts_version:fv-3",
        "metadata": {
            "asOfDate": "2026-01-01",
            "docType": template.get("doc_type", template["templateId"]),
            "documentSelection": _selection(disposition),
            "factsSnapshot": {
                "items": items,
                "entities": {"evidence": [{"entityId": "proof-1", "verificationStatus": "confirmed"}],
                             "amounts": []},
            },
            "artifactVersions": {},
            "artifacts": {},
        },
    }


def test_non_prosecution_types_are_mutually_exclusive(monkeypatch):
    template = {
        "templateId": "non-prosecution-decision", "templateVersion": "1.0.0", "contentHash": "t",
        "bodyTemplate": "被不起诉人{{facts.defendant_name.value}}",
        "fieldSchema": {
            "required": ["facts.defendant_name.value"],
            "applicability": {"document_disposition": "non_prosecution", "manual_document_selection": True},
            "exclusive_field": "non_prosecution_type",
            "mutually_exclusive": ["statutory", "discretionary", "insufficient_evidence", "conditional_minor"],
            "conditional_sections": {"fact": "non_prosecution_type", "sections": {
                "statutory": "权利告知（法定不起诉，待法学审定）：被不起诉人可以依法申诉。",
            }},
        },
    }
    monkeypatch.setattr(document_render.registry, "active_template", lambda _doc: template)
    mixed = render(_payload({"defendant_name": "张某", "non_prosecution_type": "statutory,discretionary"},
                            template, "non_prosecution"))["final_output"]
    assert mixed["status"] == "blocked" and mixed["body"] is None
    assert any(item["reason"] == "mutually_exclusive" for item in mixed["unresolved"])
    single = render(_payload({"defendant_name": "张某", "non_prosecution_type": "statutory"},
                             template, "non_prosecution"))["final_output"]
    assert single["status"] == "rendered"
    assert "法定不起诉" in single["body"]


def test_adult_conditional_non_prosecution_is_blocked(monkeypatch):
    template = {
        "templateId": "non-prosecution-decision", "templateVersion": "1.0.0", "contentHash": "t",
        "bodyTemplate": "{{facts.defendant_name.value}}",
        "fieldSchema": {
            "required": ["facts.defendant_name.value"],
            "applicability": {"document_disposition": "non_prosecution", "manual_document_selection": True},
            "exclusive_field": "non_prosecution_type",
            "mutually_exclusive": ["conditional_minor"],
            "conditional_minor_required": ["offence_age_under_18"],
            "conditional_sections": {"fact": "non_prosecution_type", "sections": {
                "conditional_minor": "权利告知（附条件不起诉，待法学审定）。",
            }},
        },
    }
    monkeypatch.setattr(document_render.registry, "active_template", lambda _doc: template)
    body = render(_payload({
        "defendant_name": "张某", "non_prosecution_type": "conditional_minor",
        "offence_age_under_18": False, "offence_age": 20,
    }, template, "non_prosecution"))["final_output"]
    assert body["status"] == "blocked"
    assert any(item["reason"] == "conditional_minor_not_applicable" for item in body["unresolved"])


def test_exemption_cannot_carry_a_principal_penalty(monkeypatch):
    template = {
        "templateId": "sentencing-recommendation", "templateVersion": "1.0.0", "contentHash": "t",
        "bodyTemplate": "{{facts.defendant_name.value}}",
        "fieldSchema": {
            "required": ["facts.defendant_name.value"],
            "applicability": {"document_disposition": "sentencing_recommendation", "manual_document_selection": True},
            "conditional_required": [
                {"fact": "exempt_from_criminal_punishment", "eq": False, "required": ["proposed_principal_penalty"]},
                {"fact": "exempt_from_criminal_punishment", "eq": True, "required": ["exemption_basis"],
                 "must_omit": ["proposed_principal_penalty"]},
            ],
        },
    }
    monkeypatch.setattr(document_render.registry, "active_template", lambda _doc: template)
    conflict = render(_payload({
        "defendant_name": "张某", "exempt_from_criminal_punishment": True,
        "exemption_basis": "法定免刑事由", "proposed_principal_penalty": "有期徒刑九个月",
    }, template, "sentencing_recommendation"))["final_output"]
    assert conflict["status"] == "blocked"
    assert any(item["reason"] == "mutually_exclusive" for item in conflict["unresolved"])


def test_unresolved_charge_boundary_blocks_indictment(monkeypatch):
    template = {
        "templateId": "indictment-assist", "templateVersion": "1.1.0", "contentHash": "t",
        "bodyTemplate": "{{facts.defendant_name.value}}",
        "fieldSchema": {
            "required": ["facts.defendant_name.value"],
            "applicability": {"document_disposition": "prosecution", "manual_document_selection": True},
        },
    }
    monkeypatch.setattr(document_render.registry, "active_template", lambda _doc: template)
    payload = _payload({"defendant_name": "张某"}, template)
    payload["metadata"]["documentSelection"]["chargeBoundaryUnresolved"] = True
    body = render(payload)["final_output"]
    assert body["status"] == "blocked"
    assert any(item["reason"] == "boundary_unresolved" for item in body["unresolved"])


def test_version_group_uses_the_covering_text_and_keeps_cross_date_divergence():
    old = {"versionGroup": "cn-cybersecurity-law", "resolutions": {
        "conduct": {"candidates": [{"sourceVersion": "2017-original"}]},
        "judgment": {"candidates": []},
    }}
    new = {"versionGroup": "cn-cybersecurity-law", "resolutions": {
        "conduct": {"candidates": []},
        "judgment": {"candidates": [{"sourceVersion": "2025-revision"}]},
    }}
    result = _reconcile_version_groups({
        "resolutions": {"cn-cybersecurity-law-2016": old, "cn-cybersecurity-law-2025": new},
        "blockers": [
            {"code": "LEGAL_SOURCE_COVERAGE_GAP", "sourceKey": "cn-cybersecurity-law-2025",
             "gaps": [{"point": "conduct"}]},
            {"code": "LEGAL_SOURCE_COVERAGE_GAP", "sourceKey": "cn-cybersecurity-law-2016",
             "gaps": [{"point": "judgment"}]},
        ],
        "divergence": [],
    })
    assert result["blockers"]
    assert all(item["code"] == "LEGAL_TEMPORAL_DIVERGENCE" for item in result["blockers"])
    assert result["divergence"][0]["code"] == "LAW_VERSION_DIVERGENCE"
