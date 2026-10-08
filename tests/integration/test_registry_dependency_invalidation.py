"""Real PostgreSQL coverage for V8 registry dependency invalidation."""
from __future__ import annotations

import os
import threading
import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from engine.api import app
from engine.rules import registry
from engine.rules.dependency_validity import GLOBAL_BARRIER_KEY, verify_coordination, verify_dependencies
from engine.settings import settings
from engine.store import connection

pytestmark = pytest.mark.integration


def _db_available() -> bool:
    try:
        with connection() as conn:
            conn.execute("SELECT 1 FROM engine.registry_invalidation_event LIMIT 0")
        return True
    except Exception:
        return False


@pytest.fixture(autouse=True)
def _require_db():
    if not _db_available():
        if os.getenv("LEXCYBER_REQUIRE_INTEGRATION_DB") == "1":
            pytest.fail("engine postgres/V8 unavailable; CI requires registry invalidation integration")
        pytest.skip("engine postgres/V8 unavailable")


def _prefix(label: str = "v8") -> str:
    return f"{label}-{uuid.uuid4().hex[:12]}"


def _source(prefix: str, *, version: str = "1") -> dict:
    return {"source_key": f"{prefix}-source", "title": "synthetic V8 source",
            "authority": "law", "source_version": version, "effective_from": "2020-01-01",
            "verification_level": "verified"}


def _rule(prefix: str, source_id: str, *, rule_id: str | None = None,
          outcome: dict | None = None, predicate: dict | None = None) -> dict:
    return {"rule_id": rule_id or f"{prefix}-rule", "rule_version": "1", "family": "compliance",
            "predicate": predicate or {"path": "facts.f1.value", "op": "eq", "value": True},
            "outcome": outcome or {"conclusion": "synthetic-v8"}, "source_ids": [source_id]}


def _approved_bundle(prefix: str | None = None, *, rule_id: str | None = None,
                     with_template: bool = True) -> dict:
    prefix = prefix or _prefix()
    source = registry.register_legal_source(_source(prefix))
    rule = registry.register_rule_package(_rule(prefix, source["sourceId"], rule_id=rule_id))
    template = registry.register_template({
        "template_id": f"{prefix}-template", "template_version": "1",
        "doc_type": "indictment", "body_template": "synthetic body",
    }) if with_template else None
    registry.signoff("legal_source", f"{prefix}-source@1", "fixture", "legal_reviewer", "approved")
    registry.signoff("rule", f"{rule_id or prefix + '-rule'}@1", "fixture", "legal_reviewer", "approved")
    if template:
        registry.signoff("template", f"{prefix}-template@1", "fixture", "legal_reviewer", "approved")
    return {"prefix": prefix, "source": source, "rule": rule, "template": template}


def _payload_set(payload: list[dict]) -> set[tuple[str, str, str]]:
    return {(item["kind"], item["key"], item["version"]) for item in payload}


def test_coordination_requires_global_and_challenge_shared_locks_and_rejects_wrong_modes():
    challenge = 918273645
    with connection() as conn:
        pid = conn.execute("SELECT pg_backend_pid()").fetchone()[0]
        conn.execute("SELECT pg_advisory_xact_lock_shared(%s)", (GLOBAL_BARRIER_KEY,))
        conn.execute("SELECT pg_advisory_xact_lock_shared(%s)", (challenge,))
        assert verify_coordination(conn, pid, str(challenge))
        assert not verify_coordination(conn, pid + 1, str(challenge))
        assert not verify_coordination(conn, pid, str(GLOBAL_BARRIER_KEY))
        assert not verify_coordination(conn, pid, str(1 << 63))

    with connection() as conn:
        pid = conn.execute("SELECT pg_backend_pid()").fetchone()[0]
        conn.execute("SELECT pg_advisory_xact_lock_shared(%s)", (GLOBAL_BARRIER_KEY,))
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (challenge,))
        assert not verify_coordination(conn, pid, str(challenge))


def test_verify_dependencies_requires_exact_effective_rule_template_source_versions():
    bundle = _approved_bundle()
    source_id = bundle["source"]["sourceId"]
    deps = [
        {"kind": "legal_source", "key": source_id, "version": "1"},
        {"kind": "rule", "key": f"{bundle['prefix']}-rule", "version": "1"},
        {"kind": "template", "key": f"{bundle['prefix']}-template", "version": "1"},
    ]
    with connection() as conn:
        assert verify_dependencies(conn, deps) == []
        invalid = verify_dependencies(conn, [
            {"kind": "legal_source", "key": "not-a-uuid", "version": "1"},
            {"kind": "legal_source", "key": source_id, "version": ""},
            {"kind": "rule", "key": f"{bundle['prefix']}-rule", "version": "2"},
            {"kind": "template", "key": f"{bundle['prefix']}-template", "version": ""},
        ])
    assert len(invalid) == 4
    assert {item["kind"] for item in invalid} == {"legal_source", "rule", "template"}


def test_dependency_verification_http_route_returns_valid_and_controlled_invalid(monkeypatch):
    bundle = _approved_bundle()
    challenge = 782341
    monkeypatch.setattr(settings, "service_token", "v8-test-token")
    client = TestClient(app)
    deps = [
        {"kind": "legal_source", "key": bundle["source"]["sourceId"], "version": "1"},
        {"kind": "rule", "key": f"{bundle['prefix']}-rule", "version": "1"},
    ]
    with connection() as conn:
        pid = conn.execute("SELECT pg_backend_pid()").fetchone()[0]
        conn.execute("SELECT pg_advisory_xact_lock_shared(%s)", (GLOBAL_BARRIER_KEY,))
        conn.execute("SELECT pg_advisory_xact_lock_shared(%s)", (challenge,))
        response = client.post("/internal/v1/registry/verify-dependencies",
                               headers={"X-Service-Token": "v8-test-token"},
                               json={"coordination": {"backendPid": pid, "challenge": str(challenge)},
                                     "dependencies": deps})
        assert response.status_code == 200
        assert response.json() == {"valid": True, "invalidDependencies": []}
        response = client.post("/internal/v1/registry/verify-dependencies",
                               headers={"X-Service-Token": "v8-test-token"},
                               json={"coordination": {"backendPid": pid, "challenge": str(challenge)},
                                     "dependencies": [{"kind": "legal_source", "key": "bad", "version": ""}]})
        assert response.status_code == 200
        assert response.json()["valid"] is False
        assert response.json()["invalidDependencies"][0]["reason"]


def test_source_withdrawal_event_contains_source_and_all_referencing_rules_including_false_rule():
    prefix = _prefix("withdraw")
    source = registry.register_legal_source(_source(prefix))
    true_rule = registry.register_rule_package(_rule(prefix, source["sourceId"], rule_id=f"{prefix}-true"))
    false_rule = registry.register_rule_package(_rule(
        prefix, source["sourceId"], rule_id=f"{prefix}-false",
        predicate={"path": "facts.f1.value", "op": "eq", "value": False}))
    registry.signoff("legal_source", f"{prefix}-source@1", "fixture", "legal_reviewer", "approved")
    registry.signoff("rule", f"{prefix}-true@1", "fixture", "legal_reviewer", "approved")
    registry.signoff("rule", f"{prefix}-false@1", "fixture", "legal_reviewer", "approved")
    with connection() as conn:
        before = conn.execute("SELECT count(*) FROM engine.registry_invalidation_event").fetchone()[0]
        conn.execute("SELECT set_config('engine.signoff_authorized', 'on', true)")
        conn.execute("UPDATE engine.legal_source SET verification_level='disputed' WHERE source_id=%s",
                     (source["sourceId"],))
        row = conn.execute(
            "SELECT dependencies FROM engine.registry_invalidation_event ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        after = conn.execute("SELECT count(*) FROM engine.registry_invalidation_event").fetchone()[0]
    assert after == before + 1
    assert _payload_set(row[0]) == {
        ("legal_source", source["sourceId"], "1"),
        ("rule", f"{prefix}-true", "1"),
        ("rule", f"{prefix}-false", "1"),
    }
    assert true_rule["rulePackageId"] and false_rule["rulePackageId"]


def test_approved_rule_template_updates_and_at_sign_signoff_delete_emit_exact_dependencies():
    prefix = _prefix("events")
    rule_id = f"{prefix}@rule"
    bundle = _approved_bundle(prefix, rule_id=rule_id)
    with connection() as conn:
        conn.execute("UPDATE engine.rule_package SET legal_review_status='superseded' WHERE rule_id=%s", (rule_id,))
        rule_event = conn.execute(
            "SELECT dependencies FROM engine.registry_invalidation_event ORDER BY created_at DESC LIMIT 1"
        ).fetchone()[0]
        conn.execute("UPDATE engine.template_package SET legal_review_status='superseded' WHERE template_id=%s", (f"{prefix}-template",))
        template_event = conn.execute(
            "SELECT dependencies FROM engine.registry_invalidation_event ORDER BY created_at DESC LIMIT 1"
        ).fetchone()[0]
        signoff_id = conn.execute(
            "SELECT signoff_id FROM engine.signoff_record WHERE subject_kind='rule' AND subject_key=%s "
            "AND decision='approved' ORDER BY signoff_id DESC LIMIT 1", (f"{rule_id}@1",)
        ).fetchone()[0]
        conn.execute("DELETE FROM engine.signoff_record WHERE signoff_id=%s", (signoff_id,))
        at_sign_event = conn.execute(
            "SELECT dependencies FROM engine.registry_invalidation_event ORDER BY created_at DESC LIMIT 1"
        ).fetchone()[0]
    assert ("rule", rule_id, "1") in _payload_set(rule_event)
    assert ("template", f"{prefix}-template", "1") in _payload_set(template_event)
    assert ("rule", rule_id, "1") in _payload_set(at_sign_event)
    assert bundle["rule"]["rulePackageId"]


def test_signed_off_source_content_is_immutable_but_same_version_reapproval_is_valid():
    bundle = _approved_bundle(_prefix("immutable"), with_template=False)
    source_id = bundle["source"]["sourceId"]
    source_key = f"{bundle['prefix']}-source"
    with pytest.raises(Exception):
        with connection() as conn:
            conn.execute("SELECT set_config('engine.signoff_authorized', 'on', true)")
            conn.execute("UPDATE engine.legal_source SET title='mutated' WHERE source_id=%s", (source_id,))
    with connection() as conn:
        row = conn.execute(
            "SELECT title, source_version, verification_level FROM engine.legal_source WHERE source_id=%s",
            (source_id,),
        ).fetchone()
    assert row == ("synthetic V8 source", "1", "signed_off")
    registry.signoff("legal_source", f"{source_key}@1", "withdrawal", "legal_reviewer", "rejected")
    with pytest.raises(Exception):
        with connection() as conn:
            conn.execute("UPDATE engine.legal_source SET title='rewritten withdrawn source' WHERE source_id=%s", (source_id,))
    registry.signoff("legal_source", f"{source_key}@1", "fixture-again", "legal_reviewer", "approved")
    with pytest.raises(Exception):
        with connection() as conn:
            conn.execute("SELECT set_config('engine.signoff_authorized', 'on', true)")
            conn.execute("UPDATE engine.legal_source SET verification_level='pending' WHERE source_id=%s", (source_id,))
    with pytest.raises(Exception):
        with connection() as conn:
            conn.execute("SELECT set_config('engine.signoff_authorized', 'on', true)")
            conn.execute("DELETE FROM engine.legal_source WHERE source_id=%s", (source_id,))


def test_signoff_comment_and_nonfinal_approved_delete_do_not_invalidate_until_last_approval():
    prefix = _prefix("signoff-refs")
    bundle = _approved_bundle(prefix, with_template=False)
    subject = f"{prefix}-rule@1"
    with connection() as conn:
        conn.execute("INSERT INTO engine.signoff_record(subject_kind,subject_key,reviewer,role,decision) "
                     "VALUES ('rule',%s,'second-fixture','legal_reviewer','approved')", (subject,))
    with connection() as conn:
        rows = conn.execute(
            "SELECT signoff_id FROM engine.signoff_record "
            "WHERE subject_kind='rule' AND subject_key=%s AND decision='approved' ORDER BY signoff_id",
            (subject,),
        ).fetchall()
        assert len(rows) == 2
        before = {row[0] for row in conn.execute(
            "SELECT event_id FROM engine.registry_invalidation_event").fetchall()}
        conn.execute("UPDATE engine.signoff_record SET comment='metadata only' WHERE signoff_id=%s", (rows[0][0],))
        after_comment = {row[0] for row in conn.execute(
            "SELECT event_id FROM engine.registry_invalidation_event").fetchall()}
        conn.execute("DELETE FROM engine.signoff_record WHERE signoff_id=%s", (rows[0][0],))
        after_first_delete = {row[0] for row in conn.execute(
            "SELECT event_id FROM engine.registry_invalidation_event").fetchall()}
        conn.execute("DELETE FROM engine.signoff_record WHERE signoff_id=%s", (rows[1][0],))
        after_last_delete = {row[0] for row in conn.execute(
            "SELECT event_id FROM engine.registry_invalidation_event").fetchall()}
        event = conn.execute(
            "SELECT dependencies FROM engine.registry_invalidation_event ORDER BY created_at DESC LIMIT 1"
        ).fetchone()[0]
    assert after_comment == before
    assert after_first_delete == before
    assert len(after_last_delete - before) == 1
    assert _payload_set(event) == {("rule", f"{prefix}-rule", "1")}
    assert bundle["rule"]["rulePackageId"]


def test_rollback_actual_source_withdrawal_leaves_state_and_event_unchanged():
    bundle = _approved_bundle(_prefix("rollback"), with_template=False)
    source_id = bundle["source"]["sourceId"]
    with connection() as conn:
        before_events = conn.execute("SELECT count(*) FROM engine.registry_invalidation_event").fetchone()[0]
        conn.rollback()
        conn.execute("SELECT set_config('engine.signoff_authorized', 'on', true)")
        conn.execute("UPDATE engine.legal_source SET verification_level='disputed' WHERE source_id=%s", (source_id,))
        conn.execute("ROLLBACK")
        source_state = conn.execute("SELECT verification_level FROM engine.legal_source WHERE source_id=%s", (source_id,)).fetchone()[0]
        after_events = conn.execute("SELECT count(*) FROM engine.registry_invalidation_event").fetchone()[0]
    assert source_state == "signed_off"
    assert after_events == before_events


def test_writer_barrier_blocks_source_withdrawal_until_global_and_challenge_shared_locks_release():
    bundle = _approved_bundle(_prefix("barrier"), with_template=False)
    source_id = bundle["source"]["sourceId"]
    challenge = 726381
    ready = threading.Event()
    finished = threading.Event()
    outcome: dict[str, object] = {}

    def withdraw() -> None:
        try:
            with connection() as conn:
                outcome["pid"] = conn.execute("SELECT pg_backend_pid()").fetchone()[0]
                outcome["started"] = conn.execute("SELECT transaction_timestamp()").fetchone()[0]
                ready.set()
                conn.execute("SELECT set_config('engine.signoff_authorized', 'on', true)")
                conn.execute("UPDATE engine.legal_source SET verification_level='disputed' WHERE source_id=%s", (source_id,))
                outcome["updated"] = True
        except Exception as exc:  # pragma: no cover
            outcome["error"] = repr(exc)
        finally:
            finished.set()

    with connection() as owner:
        owner.execute("SELECT pg_advisory_xact_lock_shared(%s)", (GLOBAL_BARRIER_KEY,))
        owner.execute("SELECT pg_advisory_xact_lock_shared(%s)", (challenge,))
        thread = threading.Thread(target=withdraw, daemon=True)
        thread.start()
        assert ready.wait(timeout=2)
        blocked = False
        for _ in range(40):
            with connection() as probe:
                blocked = probe.execute(
                    "SELECT EXISTS (SELECT 1 FROM pg_locks WHERE pid=%s AND locktype='advisory' AND NOT granted)",
                    (outcome["pid"],),
                ).fetchone()[0]
            if blocked:
                break
            time.sleep(0.05)
        assert blocked, "withdrawal did not wait on the exclusive global barrier"
        assert not finished.is_set()
        with connection() as probe:
            assert probe.execute("SELECT verification_level FROM engine.legal_source WHERE source_id=%s", (source_id,)).fetchone()[0] == "signed_off"
        owner.commit()
    assert finished.wait(timeout=5)
    thread.join(timeout=1)
    assert "error" not in outcome, outcome
    assert outcome.get("updated") is True
    with connection() as conn:
        state = conn.execute("SELECT verification_level FROM engine.legal_source WHERE source_id=%s", (source_id,)).fetchone()[0]
        event = conn.execute("SELECT dependencies, created_at FROM engine.registry_invalidation_event ORDER BY created_at DESC LIMIT 1").fetchone()
    assert state == "disputed"
    assert ("legal_source", source_id, "1") in _payload_set(event[0])
    assert event[1] > outcome["started"], "event timestamp must be after the earlier blocked transaction start"


def test_v7_to_v8_isolated_upgrade_preserves_rows_signoffs_and_effective_history():
    schema = f"v8_upgrade_{uuid.uuid4().hex[:12]}"
    migrations = Path(registry.__file__).parents[1] / "migrations"
    paths = [migrations / name for name in (
        "V6__legal_rule_registry.sql", "V7__registry_insert_review_gate.sql",
        "V8__registry_dependency_invalidation.sql")]
    assert all(path.is_file() for path in paths)

    def isolated_sql(path: Path) -> str:
        sql = path.read_text(encoding="utf-8")
        sql = sql.replace("'engine.signoff_authorized'", "'__ENGINE_SIGNOFF_GUC__'")
        sql = sql.replace("engine.", f'"{schema}".')
        return sql.replace("'__ENGINE_SIGNOFF_GUC__'", "'engine.signoff_authorized'")

    with connection() as conn:
        conn.execute(f'CREATE SCHEMA "{schema}"')
        try:
            conn.execute(isolated_sql(paths[0]))
            source_id = uuid.uuid4()
            source_key = f"{schema}-source"
            rule_id = f"{schema}-rule"
            conn.execute(
                f"INSERT INTO \"{schema}\".legal_source(source_id, source_key, title, authority, source_version, effective_from, content_hash, verification_level) "
                "VALUES (%s,%s,'source','law','1','2020-01-01','source-hash','signed_off')", (source_id, source_key))
            conn.execute(
                f"INSERT INTO \"{schema}\".rule_package(rule_id, rule_version, family, legal_review_status, source_ids, predicate, outcome, content_hash) "
                "VALUES (%s,'1','compliance','approved',%s::jsonb,'{}','{}','rule-hash')", (rule_id, f'["{source_id}"]'))
            conn.execute(
                f"INSERT INTO \"{schema}\".signoff_record(subject_kind, subject_key, reviewer, role, decision) "
                f"VALUES ('legal_source',%s,'legacy','legal_reviewer','approved'),('rule',%s,'legacy','legal_reviewer','approved')",
                (f"{source_key}@1", f"{rule_id}@1"))
            history_before = (
                conn.execute(f"SELECT source_id, source_key, verification_level FROM \"{schema}\".legal_source").fetchall(),
                conn.execute(f"SELECT rule_id, rule_version, legal_review_status, source_ids FROM \"{schema}\".rule_package").fetchall(),
                conn.execute(f"SELECT subject_kind, subject_key, decision FROM \"{schema}\".signoff_record ORDER BY subject_kind").fetchall(),
            )
            conn.execute(isolated_sql(paths[1]))
            assert conn.execute(f'SELECT count(*) FROM "{schema}".effective_legal_source').fetchone()[0] == 1
            assert conn.execute(f'SELECT count(*) FROM "{schema}".effective_rule_package').fetchone()[0] == 1
            # V7 still permits a signed_off row to be downgraded, edited while
            # disputed, and re-approved at the same version.  Demonstrate the
            # historical hole inside a savepoint, then restore the fixture
            # before applying V8 so the migration test remains isolated.
            conn.execute("SAVEPOINT v7_content_gap")
            conn.execute("SELECT set_config('engine.signoff_authorized', 'on', true)")
            conn.execute(f"UPDATE \"{schema}\".legal_source SET verification_level='disputed' WHERE source_id=%s", (source_id,))
            conn.execute(f"UPDATE \"{schema}\".legal_source SET title='mutated-v7' WHERE source_id=%s", (source_id,))
            conn.execute(f"UPDATE \"{schema}\".legal_source SET verification_level='signed_off' WHERE source_id=%s", (source_id,))
            assert conn.execute(f"SELECT title FROM \"{schema}\".effective_legal_source WHERE source_id=%s", (source_id,)).fetchone()[0] == "mutated-v7"
            conn.execute("ROLLBACK TO SAVEPOINT v7_content_gap")
            assert conn.execute(f"SELECT title FROM \"{schema}\".legal_source WHERE source_id=%s", (source_id,)).fetchone()[0] == "source"
            conn.execute(isolated_sql(paths[2]))
            assert conn.execute(f'SELECT count(*) FROM "{schema}".registry_invalidation_event').fetchone()[0] == 0
            conn.execute("SAVEPOINT v8_content_guard")
            conn.execute("SELECT set_config('engine.signoff_authorized', 'on', true)")
            with pytest.raises(Exception):
                conn.execute(f"UPDATE \"{schema}\".legal_source SET verification_level='disputed' WHERE source_id=%s", (source_id,))
                conn.execute(f"UPDATE \"{schema}\".legal_source SET title='mutated-v8' WHERE source_id=%s", (source_id,))
                conn.execute(f"UPDATE \"{schema}\".legal_source SET verification_level='signed_off' WHERE source_id=%s", (source_id,))
            conn.execute("ROLLBACK TO SAVEPOINT v8_content_guard")
            history_after = (
                conn.execute(f"SELECT source_id, source_key, verification_level FROM \"{schema}\".legal_source").fetchall(),
                conn.execute(f"SELECT rule_id, rule_version, legal_review_status, source_ids FROM \"{schema}\".rule_package").fetchall(),
                conn.execute(f"SELECT subject_kind, subject_key, decision FROM \"{schema}\".signoff_record ORDER BY subject_kind").fetchall(),
            )
            assert history_after == history_before
        finally:
            conn.execute(f'DROP SCHEMA "{schema}" CASCADE')
