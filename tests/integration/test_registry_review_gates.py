"""V7 registry insert gates and review-backed effective projections."""
from __future__ import annotations

import os
import uuid
from datetime import date
from pathlib import Path

import pytest

from engine.rules import registry
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
        if os.getenv("LEXCYBER_REQUIRE_INTEGRATION_DB") == "1":
            pytest.fail("engine postgres unavailable; CI requires real registry integration tests")
        pytest.skip("engine postgres unavailable")


def _prefix() -> str:
    return f"v7-{uuid.uuid4().hex[:10]}"


def _insert_rule(conn, rule_id: str, status: str) -> None:
    conn.execute(
        """
        INSERT INTO engine.rule_package(
            rule_id, rule_version, family, legal_review_status, predicate, outcome,
            source_ids, required_evidence_kinds, coverage, content_hash)
        VALUES (%s, '1', 'compliance', %s, '{}'::jsonb, '{}'::jsonb,
                '[]'::jsonb, '[]'::jsonb, '{}'::jsonb, %s)
        """,
        (rule_id, status, f"hash-{rule_id}"),
    )


def _insert_template(conn, template_id: str, status: str) -> None:
    conn.execute(
        """
        INSERT INTO engine.template_package(
            template_id, template_version, doc_type, legal_review_status,
            field_schema, body_template, content_hash)
        VALUES (%s, '1', 'indictment', %s, '{}'::jsonb, 'body', %s)
        """,
        (template_id, status, f"hash-{template_id}"),
    )


def _insert_source(conn, source_key: str, verification: str) -> None:
    conn.execute(
        """
        INSERT INTO engine.legal_source(
            source_key, title, authority, source_version, effective_from,
            verification_level, content_hash)
        VALUES (%s, 'source', 'law', '1', '2020-01-01', %s, %s)
        """,
        (source_key, verification, f"hash-{source_key}"),
    )


@pytest.mark.parametrize(
    ("table", "insert"),
    [
        ("engine.rule_package", lambda conn, key: _insert_rule(conn, key, "approved")),
        ("engine.template_package", lambda conn, key: _insert_template(conn, key, "approved")),
        ("engine.legal_source", lambda conn, key: _insert_source(conn, key, "signed_off")),
    ],
)
def test_reviewed_initial_insert_rejected_even_with_signoff_guc(table, insert):
    key = f"{_prefix()}-{table.rsplit('.', 1)[-1]}"
    with pytest.raises(Exception):
        with connection() as conn:
            conn.execute("SELECT set_config('engine.signoff_authorized', 'on', true)")
            insert(conn, key)
    with connection() as conn:
        if table.endswith("rule_package"):
            count = conn.execute("SELECT count(*) FROM engine.rule_package WHERE rule_id=%s", (key,)).fetchone()[0]
            signoffs = conn.execute("SELECT count(*) FROM engine.signoff_record WHERE subject_key=%s", (f"{key}@1",)).fetchone()[0]
        elif table.endswith("template_package"):
            count = conn.execute("SELECT count(*) FROM engine.template_package WHERE template_id=%s", (key,)).fetchone()[0]
            signoffs = conn.execute("SELECT count(*) FROM engine.signoff_record WHERE subject_key=%s", (f"{key}@1",)).fetchone()[0]
        else:
            count = conn.execute("SELECT count(*) FROM engine.legal_source WHERE source_key=%s", (key,)).fetchone()[0]
            signoffs = conn.execute("SELECT count(*) FROM engine.signoff_record WHERE subject_key=%s", (f"{key}@1",)).fetchone()[0]
    assert count == 0
    assert signoffs == 0


def test_pending_registration_then_signoff_is_effective_and_history_remains_immutable():
    key = _prefix()
    rule_id = f"{key}-rule"
    template_id = f"{key}-template"
    source_key = f"{key}-source"

    source = registry.register_legal_source({
        "source_key": source_key, "title": "source", "authority": "law",
        "source_version": "1", "effective_from": "2020-01-01", "verification_level": "verified",
    })
    registry.register_rule_package({
        "rule_id": rule_id, "rule_version": "1", "family": "compliance",
        "predicate": {}, "outcome": {}, "source_ids": [source["sourceId"]],
    })
    registry.register_template({
        "template_id": template_id, "template_version": "1", "doc_type": "indictment",
        "body_template": "body",
    })
    with connection() as conn:
        rule_row = conn.execute(
            "SELECT rule_package_id, source_ids, legal_review_status FROM engine.rule_package WHERE rule_id=%s", (rule_id,)
        ).fetchone()
        source_row = conn.execute(
            "SELECT source_id, verification_level FROM engine.legal_source WHERE source_key=%s", (source_key,)
        ).fetchone()
    assert rule_row[2] == "pending"
    assert source_row[1] == "verified"

    registry.signoff("legal_source", f"{source_key}@1", "reviewer", "legal_reviewer", "approved")
    registry.signoff("rule", f"{rule_id}@1", "reviewer", "legal_reviewer", "approved")
    registry.signoff("template", f"{template_id}@1", "reviewer", "legal_reviewer", "approved")

    with connection() as conn:
        assert conn.execute("SELECT count(*) FROM engine.effective_legal_source WHERE source_key=%s", (source_key,)).fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM engine.effective_rule_package WHERE rule_id=%s", (rule_id,)).fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM engine.effective_template_package WHERE template_id=%s", (template_id,)).fetchone()[0] == 1
        after = conn.execute(
            "SELECT rule_package_id, legal_review_status, source_ids FROM engine.rule_package WHERE rule_id=%s", (rule_id,)
        ).fetchone()
    assert after[0] == rule_row[0]
    assert after[2] == rule_row[1]
    assert after[1] == "approved"

    assert any(item["ruleId"] == rule_id for item in registry.active_rules("compliance", "2021-01-01"))
    caps = registry.capabilities()
    assert any(item.endswith(f"{rule_id}@1") for item in caps["modules"]["compliance"]["approvedRules"]["compliance"])
    temporal = registry.resolve_temporal(source_key, date(2021, 1, 1), None)
    assert temporal["conduct_law"]["sourceKey"] == source_key

    registry.signoff("legal_source", f"{source_key}@1", "reviewer", "legal_reviewer", "rejected")
    with connection() as conn:
        assert conn.execute("SELECT verification_level FROM engine.legal_source WHERE source_key=%s", (source_key,)).fetchone()[0] == "disputed"
        assert conn.execute("SELECT count(*) FROM engine.effective_legal_source WHERE source_key=%s", (source_key,)).fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM engine.effective_rule_package WHERE rule_id=%s", (rule_id,)).fetchone()[0] == 0
    assert not any(item["ruleId"] == rule_id for item in registry.active_rules("compliance", "2021-01-01"))
    assert not registry.resolve_temporal(source_key, date(2021, 1, 1), None).get("found")


def test_existing_approved_row_still_uses_v6_immutable_guard():
    rule_id = f"{_prefix()}-immutable"
    registry.register_rule_package({
        "rule_id": rule_id, "rule_version": "1", "family": "compliance",
        "predicate": {}, "outcome": {},
    })
    registry.signoff("rule", f"{rule_id}@1", "reviewer", "legal_reviewer", "approved")
    with pytest.raises(Exception):
        with connection() as conn:
            conn.execute("UPDATE engine.rule_package SET outcome='{}'::jsonb WHERE rule_id=%s", (rule_id,))
    with connection() as conn:
        row = conn.execute(
            "SELECT legal_review_status, outcome FROM engine.rule_package WHERE rule_id=%s", (rule_id,)
        ).fetchone()
    assert row == ("approved", {})


def test_v7_triggers_cover_all_registry_tables():
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT event_object_table, trigger_name
            FROM information_schema.triggers
            WHERE trigger_schema='engine'
              AND trigger_name IN (
                  'trg_rule_package_insert_review_gate',
                  'trg_template_insert_review_gate',
                  'trg_legal_source_insert_review_gate')
            """
        ).fetchall()
    assert {row[0] for row in rows} == {"rule_package", "template_package", "legal_source"}


def test_v6_to_v7_upgrade_preserves_history_and_filters_legacy_rows():
    schema = f"v7_upgrade_{uuid.uuid4().hex[:12]}"
    migrations = Path(registry.__file__).parents[1] / "migrations"
    v6 = migrations / "V6__legal_rule_registry.sql"
    v7 = migrations / "V7__registry_insert_review_gate.sql"
    assert v6.is_file()
    assert v7.is_file()

    def isolated_sql(path: Path) -> str:
        sql = path.read_text(encoding="utf-8")
        sql = sql.replace("'engine.signoff_authorized'", "'__ENGINE_SIGNOFF_GUC__'")
        sql = sql.replace("engine.", f'"{schema}".')
        return sql.replace("'__ENGINE_SIGNOFF_GUC__'", "'engine.signoff_authorized'")

    with connection() as conn:
        conn.execute(f'CREATE SCHEMA "{schema}"')
        try:
            conn.execute(isolated_sql(v6))
            bad_source = uuid.uuid4()
            good_source = uuid.uuid4()
            bad_rule = f"{schema}-legacy-unreviewed"
            good_rule = f"{schema}-legacy-reviewed"
            conn.execute(
                f"""
                INSERT INTO "{schema}".legal_source
                    (source_id, source_key, title, authority, source_version, effective_from,
                     content_hash, verification_level)
                VALUES (%s, %s, 'bad', 'law', '1', '2020-01-01', 'bad-hash', 'signed_off'),
                       (%s, %s, 'good', 'law', '1', '2020-01-01', 'good-hash', 'signed_off')
                """,
                (bad_source, f"{schema}-bad-source", good_source, f"{schema}-good-source"),
            )
            conn.execute(
                f"""
                INSERT INTO "{schema}".rule_package
                    (rule_id, rule_version, family, legal_review_status, source_ids,
                     predicate, outcome, content_hash)
                VALUES (%s, '1', 'compliance', 'approved', %s::jsonb, '{{}}', '{{}}', 'bad-rule-hash'),
                       (%s, '1', 'compliance', 'approved', %s::jsonb, '{{}}', '{{}}', 'good-rule-hash')
                """,
                (bad_rule, f'["{bad_source}"]', good_rule, f'["{good_source}"]'),
            )
            conn.execute(
                f"""
                INSERT INTO "{schema}".signoff_record
                    (subject_kind, subject_key, reviewer, role, decision)
                VALUES ('rule', %s, 'legacy', 'legal_reviewer', 'approved'),
                       ('legal_source', %s, 'legacy', 'legal_reviewer', 'approved'),
                       ('rule', %s, 'legacy', 'legal_reviewer', 'approved')
                """,
                (f"{good_rule}@1", f"{schema}-good-source@1", f"{bad_rule}@1"),
            )
            conn.execute(isolated_sql(v7))

            before = conn.execute(
                f"SELECT source_id, verification_level FROM \"{schema}\".legal_source ORDER BY source_key"
            ).fetchall()
            assert conn.execute(f'SELECT count(*) FROM "{schema}".effective_legal_source').fetchone()[0] == 1
            assert conn.execute(
                f"SELECT count(*) FROM \"{schema}\".effective_rule_package WHERE rule_id=%s", (good_rule,)
            ).fetchone()[0] == 1
            assert conn.execute(
                f"SELECT count(*) FROM \"{schema}\".effective_rule_package WHERE rule_id=%s", (bad_rule,)
            ).fetchone()[0] == 0

            with pytest.raises(Exception):
                with conn.transaction():
                    conn.execute(
                        f"""
                        INSERT INTO "{schema}".rule_package
                            (rule_id, rule_version, family, legal_review_status, predicate, outcome, content_hash)
                        VALUES (%s, '1', 'compliance', 'approved', '{{}}', '{{}}', 'new-hash')
                        """,
                        (f"{schema}-bypass",),
                    )
            after = conn.execute(
                f"SELECT source_id, verification_level FROM \"{schema}\".legal_source ORDER BY source_key"
            ).fetchall()
            assert after == before
        finally:
            conn.execute(f'DROP SCHEMA "{schema}" CASCADE')
