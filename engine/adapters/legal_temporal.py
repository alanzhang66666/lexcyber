"""Facts-backed legal two-point resolution helpers.

The adapters deliberately keep the case's immutable facts as the authority for
conduct and judgment dates.  A date that is present but not confirmed is a
blocking data-quality issue; a date that is absent is reported as a missing
point and is left to the existing explicit ``asOfDate`` path.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from engine.rules import registry
from engine.rules.inputs import InputValidator


def _date_items(snapshot: dict[str, Any], name: str) -> list[dict[str, Any]]:
    return [item for item in snapshot.get("items") or []
            if isinstance(item, dict) and item.get("key") == name]


def _raw_date(item: dict[str, Any]) -> Any:
    value = item.get("value")
    if isinstance(value, dict):
        return value.get("date") or value.get("value")
    return value


def resolve_case_dates(snapshot: dict[str, Any], input_validator: InputValidator | None = None) -> dict[str, Any]:
    """Resolve confirmed conduct/judgment dates from an immutable snapshot."""
    points: dict[str, date | None] = {"conduct": None, "judgment": None}
    missing: list[str] = []
    blockers: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    specs = {"conduct": ("conduct_date", "offense_date"), "judgment": ("judgment_date",)}
    for point, names in specs.items():
        grouped = {name: _date_items(snapshot, name) for name in names}
        present = [name for name in names if grouped[name]]
        if not present:
            missing.append(point)
            continue
        parsed: dict[str, list[date]] = {}
        for name in present:
            items = grouped[name]
            path = f"facts.{name}.value"
            if input_validator is not None:
                input_validator.check_path(path, phase="legal_dates", point=point)
            raw_values = [_raw_date(item) for item in items]
            if len({repr(value) for value in raw_values}) > 1:
                conflict = {"code": "LEGAL_DATE_CONFLICT", "point": point,
                            "path": path, "message": f"重复 {name} 的日期值不一致"}
                blockers.append(conflict)
                conflicts.append(conflict)
                continue
            if any(item.get("verificationStatus") != "confirmed" for item in items):
                blockers.append({"code": "LEGAL_DATE_UNVERIFIED", "path": path,
                                 "point": point,
                                 "message": f"{point} 必须是 confirmed 的不可变事实"})
                continue
            try:
                parsed[name] = [registry.parse_explicit_date(raw_values[0], path)]
            except registry.RegistryError as exc:
                blockers.append({"code": "LEGAL_DATE_INVALID", "path": path,
                                 "point": point, "message": str(exc)})
        if point == "conduct" and all(name in parsed for name in ("conduct_date", "offense_date")):
            if parsed["conduct_date"][0] != parsed["offense_date"][0]:
                conflict = {"code": "LEGAL_DATE_CONFLICT", "point": point,
                            "path": "facts.conduct_date.value,facts.offense_date.value",
                            "message": "conduct_date 与 offense_date 已确认值不一致"}
                blockers.append(conflict)
                conflicts.append(conflict)
        # conduct_date is the canonical value; offense_date is compatibility
        # fallback only when conduct_date is absent.
        chosen = ("conduct_date" if "conduct_date" in parsed else "offense_date") \
            if point == "conduct" else "judgment_date"
        if chosen in parsed:
            points[point] = parsed[chosen][0]
    return {
        "conduct": points["conduct"], "judgment": points["judgment"],
        "missing": missing, "conflicts": conflicts, "blockers": blockers,
        "input_validation": input_validator.summary() if input_validator is not None else None,
    }


def resolve_sources(source_ids: set[str], conduct: date | None,
                    judgment: date | None) -> dict[str, Any]:
    """Resolve every source key, retaining both point resolutions and blockers."""
    from engine.store import connection

    if not source_ids:
        return {"divergence": [], "source_versions": [], "resolutions": {},
                "blockers": []}
    with connection() as conn:
        rows = conn.execute(
            "SELECT source_id, source_key, source_version FROM engine.effective_legal_source "
            "WHERE source_id = ANY(%s::uuid[])", (sorted(source_ids),),
        ).fetchall()
    found_ids = {str(source_id) for source_id, _, _ in rows}
    missing_ids = sorted(str(source_id) for source_id in source_ids if str(source_id) not in found_ids)
    result: dict[str, Any] = {"divergence": [], "source_versions": [],
                              "resolutions": {}, "blockers": []}
    if missing_ids:
        result["blockers"].append({
            "code": "LEGAL_SOURCE_NOT_FOUND", "sourceIds": missing_ids,
            "message": "规则引用的法源不存在",
        })
    if conduct is None and judgment is None:
        result["source_versions"] = [
            {"sourceId": str(source_id), "sourceVersion": source_version,
             "sourceKey": source_key, "point": "as_of"}
            for source_id, source_key, source_version in rows
        ]
        result["source_versions"] = list({
            (item["sourceId"], item["sourceVersion"], item["point"]): item
            for item in result["source_versions"]
        }.values())
        return result
    for source_key in sorted({source_key for _, source_key, _ in rows}):
        resolution = registry.resolve_temporal(source_key, conduct, judgment)
        result["resolutions"][source_key] = resolution
        for issue in resolution.get("divergence", []):
            result["divergence"].append({"sourceKey": source_key, **issue})
        if resolution.get("coverageGap"):
            result["blockers"].append({
                "code": "LEGAL_SOURCE_COVERAGE_GAP", "sourceKey": source_key,
                "detail": f"{source_key} 在行为/裁判时点无覆盖版本",
                "gaps": resolution.get("gaps", []),
            })
        if resolution.get("overlap"):
            result["blockers"].append({
                "code": "LEGAL_SOURCE_VERSION_OVERLAP", "sourceKey": source_key,
                "detail": "法源有效区间重叠，无法自动选择版本",
                "overlaps": resolution.get("overlaps", []),
            })
        for point in ("conduct", "judgment"):
            point_info = (resolution.get("resolutions") or {}).get(point) or {}
            for view in point_info.get("candidates", []):
                result["source_versions"].append({
                    "sourceId": view["sourceId"], "sourceVersion": view["sourceVersion"],
                    "point": point, "sourceKey": source_key,
                    "date": point_info.get("date"),
                })
    result["source_versions"] = list({
        (item["sourceId"], item["sourceVersion"], item["point"]): item
        for item in result["source_versions"]
    }.values())
    return result


def temporal_blockers(resolution: dict[str, Any]) -> list[dict[str, Any]]:
    return list(resolution.get("blockers") or []) + [
        {"code": issue.get("code", "LEGAL_TEMPORAL_DIVERGENCE"), **issue}
        for issue in resolution.get("divergence", [])
    ]
