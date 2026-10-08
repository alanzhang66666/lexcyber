from __future__ import annotations

from datetime import date, datetime

import pytest

from engine.rules import registry


class _Cursor:
    def fetchall(self):
        return []


class _Conn:
    def __init__(self):
        self.sql = None
        self.params = None

    def execute(self, sql, params=()):
        self.sql, self.params = sql, params
        return _Cursor()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_active_rules_binds_explicit_date_and_has_no_wall_clock(monkeypatch):
    conn = _Conn()
    monkeypatch.setattr(registry, "connection", lambda: conn)
    registry.active_rules("compliance", date(2026, 1, 2))
    assert "current_date" not in conn.sql.lower()
    assert conn.params == ("compliance", date(2026, 1, 2), date(2026, 1, 2))


@pytest.mark.parametrize("value", [None, "2026-1-2", "2026-02-30", datetime(2026, 1, 2, 3)])
def test_active_rules_rejects_missing_invalid_or_datetime(value):
    with pytest.raises(registry.RegistryError, match="date") as err:
        registry.active_rules("compliance", value)
    assert err.value.code == "INVALID_AS_OF_DATE"
