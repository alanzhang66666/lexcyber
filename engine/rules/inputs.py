"""Fail-closed validation of the inputs actually read by a rule.

The evaluator deliberately keeps the historical predicate semantics (including
lazy ``all``/``any`` short-circuiting).  This module supplies the separate
proof that every path which was actually read came from a confirmed, identified
snapshot row with a complete evidence closure.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

_ADMINISTRATIVE_PATHS = {"case_id", "doc_type"}
_ENTITY_KEYS = ("actors", "events", "evidence", "amounts", "jurisdictionConnections")
_FACT_FIELDS = {"value", "key", "stage", "verificationStatus", "sourceVersion",
                "attributes", "entityId", "id", "externalId", "evidenceIds"}


class InputValidator:
    def __init__(self, snapshot: dict[str, Any], view: dict[str, Any]):
        self.snapshot = snapshot if isinstance(snapshot, dict) else {}
        self.view = view if isinstance(view, dict) else {}
        self._checks: list[dict[str, Any]] = []
        self._blockers: list[dict[str, Any]] = []
        self._seen: set[tuple[str, str, str]] = set()
        self._result_by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        self._fact_rows = self._rows(self.snapshot.get("items"), "facts")
        entities = self.snapshot.get("entities")
        self._entities = entities if isinstance(entities, dict) else {}
        self._shape_blockers: dict[str, dict[str, Any]] = {}
        if self.snapshot.get("items") is not None and (
                not isinstance(self.snapshot.get("items"), list)
                or any(not isinstance(row, dict) for row in self.snapshot.get("items"))):
            self._shape_blockers["facts"] = {"code": "INPUT_SCHEMA_INVALID", "reason": "facts items must be objects"}
        for section in _ENTITY_KEYS:
            raw = self._entities.get(section)
            if raw is not None and (not isinstance(raw, list)
                                    or any(not isinstance(row, dict) for row in raw)):
                self._shape_blockers[section] = {
                    "code": "INPUT_SCHEMA_INVALID", "reason": f"{section} rows must be objects"}
        self._evidence_aliases, self._evidence_ambiguities = self._alias_index(
            self._rows(self._entities.get("evidence"), "evidence"))

    @staticmethod
    def _rows(raw: Any, section: str) -> list[dict[str, Any]]:
        if raw is None:
            return []
        if not isinstance(raw, list):
            return []
        return [row for row in raw if isinstance(row, dict)]

    @staticmethod
    def _status(row: dict[str, Any]) -> Any:
        return row.get("verificationStatus", row.get("verification_status"))

    @staticmethod
    def _alias(raw: Any) -> str | None:
        if not isinstance(raw, str) or not raw.strip():
            return None
        value = raw.strip()
        try:
            return str(UUID(value)).lower()
        except (ValueError, AttributeError):
            return f"external:{value}"

    def _identity(self, row: dict[str, Any], kind: str) -> tuple[str | None, list[str], str | None]:
        raw_entity = row.get("entityId")
        raw_id = row.get("id")
        # externalId is only an alias of an identified row, never a substitute
        # for its canonical identity (or the supported legacy id).
        if raw_entity is None and raw_id is None:
            return None, [], "INPUT_IDENTITY_INVALID"
        aliases: list[str] = []
        if raw_entity is not None:
            key = self._alias(raw_entity)
            if key is None:
                return None, [], "INPUT_IDENTITY_INVALID"
            aliases.append(key)
        if raw_id is not None:
            key = self._alias(raw_id)
            if key is None:
                return None, [], "INPUT_IDENTITY_INVALID"
            aliases.append(key)
        external = row.get("externalId")
        if external is not None:
            key = self._alias(external)
            if key is None:
                return None, [], "INPUT_IDENTITY_INVALID"
            aliases.append(key)
        if not aliases:
            return None, [], "INPUT_IDENTITY_INVALID"
        canonical = aliases[0]
        # Distinct aliases may identify the same row, but a UUID/entity alias
        # cannot silently point at a different canonical identity.
        return canonical, list(dict.fromkeys(aliases)), None

    def _alias_index(self, rows: list[dict[str, Any]]) -> tuple[dict[str, str], set[str]]:
        aliases: dict[str, str] = {}
        ambiguous: set[str] = set()
        canonical_seen: set[str] = set()
        aliases_by_canonical: dict[str, set[str]] = {}
        for row in rows:
            canonical, row_aliases, _ = self._identity(row, "evidence")
            if canonical is None:
                continue
            if canonical in canonical_seen:
                ambiguous.add(canonical)
            canonical_seen.add(canonical)
            aliases_by_canonical.setdefault(canonical, set()).update(row_aliases)
            for alias in row_aliases:
                previous = aliases.get(alias)
                if previous is not None and previous != canonical:
                    ambiguous.add(alias)
                elif previous is not None and canonical in ambiguous:
                    ambiguous.add(alias)
                else:
                    aliases[alias] = canonical
        for canonical, row_aliases in aliases_by_canonical.items():
            if sum(1 for row in rows if self._identity(row, "evidence")[0] == canonical) > 1:
                ambiguous.update(row_aliases)
        return aliases, ambiguous

    def _evidence_ids(self, row: dict[str, Any], *, required: bool) -> tuple[list[str], list[dict[str, Any]]]:
        raw = row.get("evidenceIds")
        if raw is None:
            raw = row.get("evidence_ids")
        blockers: list[dict[str, Any]] = []
        if required and "evidence" in self._shape_blockers:
            blockers.append(self._shape_blockers["evidence"])
        if not isinstance(raw, list):
            if required:
                blockers.append({"code": "INPUT_EVIDENCE_INVALID", "reason": "evidenceIds must be a non-empty array"})
            return [], blockers
        if required and not raw:
            blockers.append({"code": "INPUT_EVIDENCE_INVALID", "reason": "evidenceIds must be a non-empty array"})
        resolved: list[str] = []
        seen: set[str] = set()
        for value in raw:
            if not isinstance(value, str) or not value.strip():
                blockers.append({"code": "INPUT_EVIDENCE_INVALID", "reason": "evidenceIds entries must be strings"})
                continue
            alias = self._alias(value)
            if alias in self._evidence_ambiguities:
                blockers.append({"code": "INPUT_EVIDENCE_AMBIGUOUS", "reason": value})
                continue
            canonical = self._evidence_aliases.get(alias or "")
            if canonical is None:
                blockers.append({"code": "INPUT_EVIDENCE_INVALID", "reason": value})
                continue
            if canonical in seen:
                blockers.append({"code": "INPUT_EVIDENCE_INVALID", "reason": "duplicate evidence reference"})
                continue
            seen.add(canonical)
            resolved.append(canonical)
            evidence_row = next((r for r in self._rows(self._entities.get("evidence"), "evidence")
                                 if self._identity(r, "evidence")[0] == canonical), None)
            if evidence_row is None or self._status(evidence_row) != "confirmed":
                blockers.append({"code": "INPUT_UNCONFIRMED", "reason": value})
        return resolved, blockers

    def _row_blockers(self, row: dict[str, Any], kind: str, *, evidence_required: bool = True) -> tuple[list[str], list[str], list[dict[str, Any]]]:
        input_id, _, identity_error = self._identity(row, kind)
        blockers: list[dict[str, Any]] = []
        if identity_error:
            blockers.append({"code": identity_error, "reason": f"{kind} identity is missing or invalid"})
        if kind == "evidence" and input_id in self._evidence_ambiguities:
            blockers.append({"code": "INPUT_EVIDENCE_AMBIGUOUS", "reason": "duplicate evidence identity"})
        if self._status(row) != "confirmed":
            blockers.append({"code": "INPUT_UNCONFIRMED", "reason": f"{kind} is not confirmed"})
        evidence_ids, evidence_blockers = self._evidence_ids(row, required=evidence_required)
        blockers.extend(evidence_blockers)
        return ([input_id] if input_id else []), evidence_ids, blockers

    def _record(self, path: str, phase: str, point: str, input_ids: list[str], evidence_ids: list[str], blockers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        key = (phase, point, path)
        if key in self._seen:
            previous = self._result_by_key[key]
            if blockers and not previous:
                for blocker in blockers:
                    item = {"path": path, "phase": phase, "point": point, **blocker}
                    self._blockers.append(item)
                for check in self._checks:
                    if (check["phase"], check["point"], check["path"]) == key:
                        check["status"] = "blocked"
                        break
                self._result_by_key[key] = list(blockers)
                return blockers
            return list(previous)
        self._seen.add(key)
        status = "blocked" if blockers else "verified"
        check = {"path": path, "phase": phase, "point": point, "status": status,
                 "inputIds": input_ids, "evidenceIds": evidence_ids}
        self._checks.append(check)
        self._result_by_key[key] = list(blockers)
        for blocker in blockers:
            item = {"path": path, "phase": phase, "point": point, **blocker}
            self._blockers.append(item)
        return blockers

    def _block(self, path: str, phase: str, point: str, code: str, reason: str) -> list[dict[str, Any]]:
        return self._record(path, phase, point, [], [], [{"code": code, "reason": reason}])

    def record_external(self, path: str, input_ids: list[str] | None = None,
                        evidence_ids: list[str] | None = None,
                        blockers: list[dict[str, Any]] | None = None,
                        *, phase: str = "predicate", point: str = "as_of") -> list[dict[str, Any]]:
        """Record proof produced by another phase of this same execution."""
        return self._record(path, phase, point, input_ids or [], evidence_ids or [], blockers or [])

    def merge_summary(self, summary: dict[str, Any], *, phase: str = "predicate",
                      point: str = "as_of") -> list[dict[str, Any]]:
        """Merge explicit checks and blockers; an external status is not trusted."""
        if not isinstance(summary, dict):
            return self._block("<external>", phase, point, "INPUT_SCHEMA_INVALID", "summary must be an object")
        for item in summary.get("checks", []):
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                continue
            self.record_external(item["path"], item.get("inputIds"), item.get("evidenceIds"),
                                 [], phase=item.get("phase", phase), point=item.get("point", point))
        blockers: list[dict[str, Any]] = []
        for item in summary.get("blockers", []):
            if not isinstance(item, dict):
                continue
            blocker = {"code": item.get("code", "INPUT_EXTERNAL_BLOCKED"),
                       "reason": item.get("reason", "external blocker")}
            blockers.extend(self.record_external(item.get("path", "<external>"),
                                                  item.get("inputIds"), item.get("evidenceIds"),
                                                  [blocker], phase=item.get("phase", phase),
                                                  point=item.get("point", point)))
        return blockers

    @staticmethod
    def _resolve_row_path(row: dict[str, Any], segments: list[str]) -> tuple[bool, Any]:
        node: Any = row
        for segment in segments:
            if not isinstance(node, dict) or segment not in node:
                return False, None
            node = node[segment]
        return True, node

    def check_path(self, path: str, *, phase: str = "predicate", point: str = "as_of", structural: bool = False) -> list[dict[str, Any]]:
        if not isinstance(path, str) or not path:
            return self._block(str(path), phase, point, "INPUT_PATH_UNKNOWN", "path must be a non-empty string")
        if path in _ADMINISTRATIVE_PATHS:
            if phase != "document":
                return self._block(path, phase, point, "INPUT_PATH_UNKNOWN", "administrative path is document-only")
            return self._record(path, phase, point, [], [], [])
        parts = path.split(".")
        if parts[0] == "facts" and len(parts) >= 2:
            key = parts[1]
            rows = [row for row in self._fact_rows if str(row.get("key")) == key]
            if not rows:
                if structural:
                    return self._record(path, phase, point, [], [], [])
                return self._block(path, phase, point, "INPUT_MISSING", "fact path is missing")
            if len(parts) >= 3 and parts[2] not in _FACT_FIELDS:
                return self._block(path, phase, point, "INPUT_PATH_UNKNOWN", "unknown fact field")
            shape = self._shape_blockers.get("facts")
            if shape:
                return self._record(path, phase, point, [], [], [shape])
            if len(rows) > 1:
                return self._record(path, phase, point, [], [], [{"code": "INPUT_AMBIGUOUS", "reason": "duplicate fact key"}])
            ids, evidence, blockers = self._row_blockers(rows[0], "fact")
            if len(parts) >= 3:
                found, value = self._resolve_row_path(rows[0], parts[2:])
                if (not found or value is None) and not structural:
                    blockers.append({"code": "INPUT_MISSING", "reason": "fact field is missing or null"})
            return self._record(path, phase, point, ids, evidence, blockers)
        if parts[0] == "amounts" and len(parts) >= 3 and parts[2] == "items":
            if "amounts" in self._shape_blockers:
                return self._block(path, phase, point, "INPUT_SCHEMA_INVALID", "amount rows must be objects")
            rows = [row for row in self._rows(self._entities.get("amounts"), "amounts")
                    if str(row.get("kind") or "unknown") == parts[1]]
            if len(parts) < 4 or not parts[3].isdigit():
                return self._block(path, phase, point, "INPUT_PATH_UNKNOWN", "amount item index is invalid")
            index = int(parts[3])
            if index >= len(rows):
                return self._block(path, phase, point, "INPUT_MISSING", "amount item is missing")
            ids, evidence, blockers = self._row_blockers(rows[index], "amount")
            if len(parts) > 4:
                found, value = self._resolve_row_path(rows[index], parts[4:])
                if (not found or value is None) and not structural:
                    blockers.append({"code": "INPUT_MISSING", "reason": "amount field is missing or null"})
            return self._record(path, phase, point, ids, evidence, blockers)
        if parts[0] == "amounts" and len(parts) == 3:
            kind, aggregate = parts[1], parts[2]
            if "amounts" in self._shape_blockers:
                return self._block(path, phase, point, "INPUT_SCHEMA_INVALID", "amount rows must be objects")
            metadata = self.view.get("_input_rows", {}).get("amounts", {}).get(kind, {})
            rows = metadata.get(aggregate)
            if rows is None:
                if not self._rows(self._entities.get("amounts"), "amounts"):
                    return self._block(path, phase, point, "INPUT_EMPTY", "amount aggregate has no contributors")
                return self._block(path, phase, point, "INPUT_PATH_UNKNOWN", "unknown amount aggregate")
            invalid = self.view.get("_input_invalid", {}).get("amounts", {}).get(kind, {}).get(aggregate, [])
            if invalid:
                return self._record(path, phase, point, [], [], [{"code": "INPUT_INVALID_NUMERIC", "reason": "amount contributor is not numeric"}])
            if not rows:
                return self._block(path, phase, point, "INPUT_EMPTY", "amount aggregate has no contributors")
            input_ids: list[str] = []
            evidence_ids: list[str] = []
            blockers: list[dict[str, Any]] = []
            for row in rows:
                ids, evidences, row_blockers = self._row_blockers(row, "amount")
                input_ids.extend(ids)
                evidence_ids.extend(evidences)
                blockers.extend(row_blockers)
            return self._record(path, phase, point, input_ids, evidence_ids, blockers)
        if parts[0] == "entities" and len(parts) >= 2:
            section = parts[1]
            if section not in _ENTITY_KEYS:
                return self._block(path, phase, point, "INPUT_PATH_UNKNOWN", "unknown entity section")
            rows = self._rows(self._entities.get(section), section)
            indexed = (len(parts) >= 4 and parts[2] == "items"
                       and parts[3].isdigit())
            if len(parts) > 3 and not indexed or (len(parts) == 3 and parts[2] not in {"count", "items"}):
                return self._block(path, phase, point, "INPUT_PATH_UNKNOWN", "unknown entity path")
            if section in self._shape_blockers:
                return self._block(path, phase, point, "INPUT_SCHEMA_INVALID", self._shape_blockers[section]["reason"])
            if indexed:
                index = int(parts[3])
                if index >= len(rows):
                    return self._block(path, phase, point, "INPUT_MISSING", "entity item is missing")
                rows = [rows[index]]
            if not rows:
                return self._block(path, phase, point, "INPUT_EMPTY", "entity section is empty")
            input_ids: list[str] = []
            evidence_ids: list[str] = []
            blockers: list[dict[str, Any]] = []
            if section in self._shape_blockers:
                blockers.append(self._shape_blockers[section])
            for row in rows:
                if section in {"actors", "events"}:
                    ids, _, row_blockers = self._row_blockers(row, section[:-1], evidence_required=False)
                    row_blockers.append({"code": "INPUT_ACTOR_EVIDENCE_MISSING", "reason": "actor/event has no native evidence proof"})
                    input_ids.extend(ids)
                    blockers.extend(row_blockers)
                elif section == "evidence":
                    ids, _, row_blockers = self._row_blockers(row, "evidence", evidence_required=False)
                    input_ids.extend(ids)
                    blockers.extend(row_blockers)
                else:
                    ids, evidences, row_blockers = self._row_blockers(row, section.rstrip("s"))
                    input_ids.extend(ids)
                    evidence_ids.extend(evidences)
                    blockers.extend(row_blockers)
                if indexed and len(parts) > 4:
                    found, value = self._resolve_row_path(row, parts[4:])
                    if (not found or value is None) and not structural:
                        blockers.append({"code": "INPUT_MISSING", "reason": "entity field is missing or null"})
            return self._record(path, phase, point, input_ids, evidence_ids, blockers)
        return self._block(path, phase, point, "INPUT_PATH_UNKNOWN", "path is outside the input schema")

    def check_trace(self, trace: list[dict[str, Any]], *, phase: str = "predicate", point: str = "as_of") -> list[dict[str, Any]]:
        blockers: list[dict[str, Any]] = []
        if not isinstance(trace, list):
            return self._block("<trace>", phase, point, "INPUT_PATH_UNKNOWN", "trace must be a list")
        for item in trace:
            if not isinstance(item, dict):
                blockers.extend(self._block("<trace>", phase, point, "INPUT_PATH_UNKNOWN", "trace entry must be an object"))
                continue
            path = item.get("path")
            structural = item.get("op") in {"exists", "missing"} and not item.get("found", False)
            blockers.extend(self.check_path(path, phase=phase, point=point, structural=structural))
        return blockers

    def summary(self) -> dict[str, Any]:
        return {"schema_version": "case.input-validation.v1",
                "status": "blocked" if self._blockers else "verified",
                "checks": list(self._checks), "blockers": list(self._blockers)}
