from __future__ import annotations

from datetime import date

from engine.adapters import legal_temporal
from engine.rules import registry


def test_dates_require_confirmed_fact_and_keep_missing_point():
    snapshot = {
        "items": [
            {"key": "conduct_date", "value": "2024-03-01", "verificationStatus": "confirmed"},
            {"key": "judgment_date", "value": "2026-02-01", "verificationStatus": "candidate"},
        ]
    }
    resolved = legal_temporal.resolve_case_dates(snapshot)
    assert resolved["conduct"] == date(2024, 3, 1)
    assert resolved["judgment"] is None
    assert resolved["missing"] == []
    assert resolved["blockers"][0]["code"] == "LEGAL_DATE_UNVERIFIED"


def test_offense_date_is_compatibility_alias():
    resolved = legal_temporal.resolve_case_dates({
        "items": [{"key": "offense_date", "value": "2024-03-01",
                   "verificationStatus": "confirmed"}]
    })
    assert resolved["conduct"] == date(2024, 3, 1)
    assert resolved["missing"] == ["judgment"]


def test_conduct_and_judgment_are_independent_points():
    resolved = legal_temporal.resolve_case_dates({
        "items": [
            {"key": "conduct_date", "value": "2024-03-01", "verificationStatus": "confirmed"},
            {"key": "judgment_date", "value": "2026-02-01", "verificationStatus": "confirmed"},
        ]
    })
    assert resolved["conduct"] == date(2024, 3, 1)
    assert resolved["judgment"] == date(2026, 2, 1)


def test_conduct_and_offense_conflict_is_blocking():
    resolved = legal_temporal.resolve_case_dates({
        "items": [
            {"key": "conduct_date", "value": "2024-03-01", "verificationStatus": "confirmed"},
            {"key": "offense_date", "value": "2024-04-01", "verificationStatus": "confirmed"},
        ]
    })
    assert any(item["code"] == "LEGAL_DATE_CONFLICT" for item in resolved["blockers"])


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class _Conn:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, *_args):
        return _Cursor(self.rows)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_registry_reports_all_overlapping_candidates_without_picking_one(monkeypatch):
    rows = [
        ("id-old", "law-x", "v1", date(2020, 1, 1), date(2025, 12, 31), None,
         "verified", "law", "Test law", "art. 1", "N-1", "CN", None, "old", None, {"covers": ["x"]}),
        ("id-new", "law-x", "v2", date(2025, 1, 1), None, None,
         "verified", "law", "Test law", "art. 1", "N-1", "CN", None, "new", None, {"covers": ["x"]}),
    ]
    monkeypatch.setattr(registry, "connection", lambda: _Conn(rows))
    resolved = registry.resolve_temporal("law-x", date(2025, 6, 1), None)
    assert resolved["overlap"] is True
    assert len(resolved["overlaps"][0]["candidates"]) == 2
    assert "conduct_law" not in resolved
    assert any(item["code"] == "LAW_VERSION_OVERLAP" for item in resolved["divergence"])


def test_source_lookup_reports_referenced_id_that_is_absent(monkeypatch):
    import engine.store

    monkeypatch.setattr(engine.store, "connection",
                        lambda: _Conn([("present-id", "law-x", "v1")]))
    monkeypatch.setattr(registry, "resolve_temporal", lambda *_: {
        "found": True, "coverageGap": False, "divergence": [], "overlap": False,
        "resolutions": {"conduct": {"date": "2024-01-01", "candidates": []},
                         "judgment": {"date": "2026-01-01", "candidates": []}},
    })
    resolved = legal_temporal.resolve_sources(
        {"present-id", "missing-id"}, date(2024, 1, 1), date(2026, 1, 1))
    assert any(item["code"] == "LEGAL_SOURCE_NOT_FOUND"
               for item in resolved["blockers"])
