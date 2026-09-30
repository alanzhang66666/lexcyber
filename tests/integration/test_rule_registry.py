"""P5 注册表集成测试：真实 engine schema（V6）。

覆盖：登记/重复拒绝/会签门禁/approved 不可变/退役/双时点解析/覆盖缺口/能力声明。
需要可达的 ENGINE_DATABASE_URL；不可达时 skip。
"""
from __future__ import annotations

import datetime
import uuid

import pytest

from engine.rules import registry
from engine.rules.registry import RegistryError
from engine.store import connection

pytestmark = pytest.mark.integration


def _db_available() -> bool:
    try:
        with connection() as conn:
            conn.execute("SELECT 1 FROM engine.rule_package LIMIT 0")
        return True
    except Exception:
        return False


@pytest.fixture(autouse=True)
def _require_db():
    if not _db_available():
        pytest.skip("engine postgres unavailable")


@pytest.fixture()
def subject_prefix():
    return f"it-{uuid.uuid4().hex[:8]}"


def _source(key: str, version: str, frm: str, to: str | None = None):
    return {
        "source_key": key, "title": "测试法源", "authority": "judicial_interpretation",
        "source_version": version, "effective_from": frm, "effective_to": to,
        "verification_level": "pending", "coverage": {"covers": [f"cov.{key}"]},
    }


def _rule(rid: str, version: str, family: str = "compliance", sources=None, covers=None):
    return {
        "rule_id": rid, "rule_version": version, "family": family,
        "predicate": {"all": [{"path": "facts.f1.value", "op": "eq", "value": True}]},
        "outcome": {"conclusion": "ok"},
        "source_ids": sources or [],
        "coverage": {"covers": covers or [f"cov.{rid}"]},
    }


def test_register_duplicate_rejected(subject_prefix):
    key = f"{subject_prefix}-src"
    registry.register_legal_source(_source(key, "v1", "2020-01-01"))
    with pytest.raises(RegistryError) as err:
        registry.register_legal_source(_source(key, "v1", "2020-01-01"))
    assert err.value.code == "LEGAL_SOURCE_EXISTS"


def test_registration_rejects_client_supplied_approval_status(subject_prefix):
    with pytest.raises(RegistryError) as source_error:
        registry.register_legal_source({
            **_source(f"{subject_prefix}-status", "v1", "2020-01-01"),
            "verification_level": "signed_off",
        })
    assert source_error.value.code == "LEGAL_SOURCE_SIGNOFF_REQUIRED"

    with pytest.raises(RegistryError) as rule_error:
        registry.register_rule_package({
            **_rule(f"{subject_prefix}-status-rule", "1"),
            "legal_review_status": "approved",
        })
    assert rule_error.value.code == "RULE_SIGNOFF_REQUIRED"

    with pytest.raises(RegistryError) as template_error:
        registry.register_template({
            "template_id": f"{subject_prefix}-status-template",
            "template_version": "1",
            "doc_type": "memo",
            "body_template": "正文",
            "legal_review_status": "approved",
        })
    assert template_error.value.code == "TEMPLATE_SIGNOFF_REQUIRED"


def test_rule_approval_requires_signed_off_sources(subject_prefix):
    source_key = f"{subject_prefix}-source"
    source_id = registry.register_legal_source(_source(source_key, "v1", "2020-01-01"))["sourceId"]
    rule_id = f"{subject_prefix}-rule-source"
    registry.register_rule_package(_rule(rule_id, "1", sources=[source_id]))

    with pytest.raises(RegistryError) as error:
        registry.signoff("rule", f"{rule_id}@1", "it-reviewer", "reviewer", "approved")
    assert error.value.code == "LEGAL_SOURCE_SIGNOFF_REQUIRED"

    registry.signoff("legal_source", f"{source_key}@v1", "it-reviewer", "reviewer", "approved")
    registry.signoff("rule", f"{rule_id}@1", "it-reviewer", "reviewer", "approved")
    assert any(row["ruleId"] == rule_id for row in registry.active_rules("compliance"))


def test_capabilities_exclude_approved_rule_with_unsigned_source(subject_prefix):
    source_key = f"{subject_prefix}-cap-source"
    source_id = registry.register_legal_source(_source(source_key, "v1", "2020-01-01"))["sourceId"]
    rule_id = f"{subject_prefix}-cap-rule"
    registry.register_rule_package(_rule(rule_id, "1", sources=[source_id]))
    with connection() as conn:
        conn.execute("SELECT set_config('engine.signoff_authorized','on',true)")
        conn.execute(
            "UPDATE engine.rule_package SET legal_review_status='approved' WHERE rule_id=%s",
            (rule_id,),
        )

    assert not any(row["ruleId"] == rule_id for row in registry.active_rules("compliance"))
    capabilities = registry.capabilities()
    assert rule_id not in capabilities["modules"]["compliance"]["approvedRules"]["compliance"]


def test_signoff_required_for_approval(subject_prefix):
    rid = f"{subject_prefix}-rule"
    registry.register_rule_package(_rule(rid, "1"))
    # 直接 UPDATE 绕过 signoff → 触发器拒绝
    with pytest.raises(Exception):
        with connection() as conn:
            conn.execute(
                "UPDATE engine.rule_package SET legal_review_status='approved' WHERE rule_id=%s",
                (rid,))
    # signoff 路径批准
    out = registry.signoff("rule", f"{rid}@1", "it-reviewer", "reviewer", "approved")
    assert out["decision"] == "approved"
    assert any(r["ruleId"] == rid for r in registry.active_rules("compliance"))


def test_rejected_needs_signoff(subject_prefix):
    rid = f"{subject_prefix}-rej"
    registry.register_rule_package(_rule(rid, "1"))
    with pytest.raises(Exception):
        with connection() as conn:
            conn.execute(
                "UPDATE engine.rule_package SET legal_review_status='rejected' WHERE rule_id=%s",
                (rid,))
    registry.signoff("rule", f"{rid}@1", "it-reviewer", "reviewer", "rejected")
    assert not any(r["ruleId"] == rid for r in registry.active_rules("compliance"))


def test_approved_immutable_and_supersede(subject_prefix):
    rid = f"{subject_prefix}-imm"
    registry.register_rule_package(_rule(rid, "1"))
    registry.signoff("rule", f"{rid}@1", "it-reviewer", "reviewer", "approved")
    # approved 内容不可改
    with pytest.raises(Exception):
        with connection() as conn:
            conn.execute("UPDATE engine.rule_package SET outcome='{}' WHERE rule_id=%s", (rid,))
    # approved → superseded 允许（走会签 GUC）
    with connection() as conn:
        conn.execute("SELECT set_config('engine.signoff_authorized','on',true)")
        conn.execute(
            "UPDATE engine.rule_package SET legal_review_status='superseded' WHERE rule_id=%s", (rid,))
    assert not any(r["ruleId"] == rid for r in registry.active_rules("compliance"))


def test_unknown_source_binding_rejected(subject_prefix):
    with pytest.raises(RegistryError) as err:
        registry.register_rule_package(
            _rule(f"{subject_prefix}-badbind", "1", sources=[str(uuid.uuid4())]))
    assert err.value.code == "UNKNOWN_LEGAL_SOURCE"


def test_temporal_divergence_and_gap(subject_prefix):
    key = f"{subject_prefix}-div"
    registry.register_legal_source(_source(key, "old", "2010-01-01", "2019-12-31"))
    registry.register_legal_source(_source(key, "new", "2020-01-01"))
    divergent = registry.resolve_temporal(
        key, datetime.date(2015, 6, 1), datetime.date(2021, 6, 1))
    assert divergent["divergence"], "conduct/judgment 跨版本必须产生 divergence"
    assert divergent["conduct_law"]["sourceVersion"] == "old"
    assert divergent["judgment_law"]["sourceVersion"] == "new"
    same = registry.resolve_temporal(key, datetime.date(2021, 1, 1), datetime.date(2021, 2, 1))
    assert not same["divergence"]
    gap = registry.resolve_temporal(key, datetime.date(2005, 1, 1), None)
    assert gap["coverageGap"], "区间外时点必须返回覆盖缺口而非近似"


def test_template_signoff(subject_prefix):
    tid = f"{subject_prefix}-tpl"
    registry.register_template({
        "template_id": tid, "template_version": "1", "doc_type": "indictment",
        "field_schema": {"fields": []}, "body_template": "正文",
    })
    registry.signoff("template", f"{tid}@1", "it-reviewer", "reviewer", "approved")
    caps = registry.capabilities()
    assert any(t["templateId"] == tid for t in caps["templates"])


def test_capabilities_reflect_approved(subject_prefix):
    caps = registry.capabilities()
    for module in ("compliance", "conviction", "sentencing"):
        assert module in caps["modules"]
        assert isinstance(caps["modules"][module]["available"], bool)
