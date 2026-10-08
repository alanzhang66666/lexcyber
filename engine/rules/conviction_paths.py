"""Declared, actor-scoped conviction candidate paths.

Candidate paths are intentionally a small execution DSL.  The rule outcome
declares the paths and the parent rule's fired result selects the branch; this
module never derives a path from legacy outcome fields or from a predicate.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

_POSITIONS = {"candidate", "alternative_to_examine", "excluded"}
_MISSING = object()
_FIELDS = {"path_id", "label", "charge_key", "actor_fact_key", "supporting_fact_keys",
           "contrary_fact_keys", "when_true", "when_false", "subjective"}


def _block(code: str, reason: str, path: str | None = None) -> dict[str, str]:
    item = {"code": code, "reason": reason}
    if path:
        item["path"] = path
    return item


def _definitions(outcome: Any) -> Any:
    return outcome.get("candidate_paths", _MISSING) if isinstance(outcome, dict) else _MISSING


def validate_candidate_path_definitions(outcome: Any) -> list[dict[str, str]]:
    """Return structural blockers for an outcome's declared path DSL."""
    raw = _definitions(outcome)
    if raw is _MISSING:
        return []
    blockers: list[dict[str, str]] = []
    if not isinstance(raw, list) or not raw:
        return [_block("CONVICTION_PATH_DEFINITIONS_INVALID",
                       "candidate_paths must be a non-empty array",
                       "outcome.candidate_paths")]
    ids: set[str] = set()
    required = {"path_id", "label", "charge_key", "actor_fact_key",
                "supporting_fact_keys", "contrary_fact_keys", "when_true", "when_false"}
    for index, item in enumerate(raw):
        prefix = f"outcome.candidate_paths[{index}]"
        if not isinstance(item, dict):
            blockers.append(_block("CONVICTION_PATH_DEFINITION_INVALID", "entry must be an object", prefix))
            continue
        unknown = sorted(set(item) - _FIELDS)
        if unknown:
            blockers.append(_block("CONVICTION_PATH_DEFINITION_INVALID", f"unknown fields: {unknown}", prefix))
        missing = sorted(required - set(item))
        if missing:
            blockers.append(_block("CONVICTION_PATH_DEFINITION_INVALID", f"missing fields: {missing}", prefix))
        path_id = item.get("path_id")
        if not isinstance(path_id, str) or not path_id.strip():
            blockers.append(_block("CONVICTION_PATH_DEFINITION_INVALID", "path_id must be nonblank", f"{prefix}.path_id"))
        elif path_id in ids:
            blockers.append(_block("CONVICTION_PATH_DUPLICATE", "duplicate path_id", f"{prefix}.path_id"))
        else:
            ids.add(path_id)
        for key in ("label", "charge_key", "actor_fact_key"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                blockers.append(_block("CONVICTION_PATH_DEFINITION_INVALID", f"{key} must be nonblank", f"{prefix}.{key}"))
            elif key == "actor_fact_key" and "." in item[key]:
                blockers.append(_block("CONVICTION_PATH_DEFINITION_INVALID", f"{key} must be a fact key without dots", f"{prefix}.{key}"))
        if "subjective" in item and not isinstance(item["subjective"], bool):
            blockers.append(_block("CONVICTION_PATH_DEFINITION_INVALID", "subjective must be boolean", f"{prefix}.subjective"))
        for key in ("supporting_fact_keys", "contrary_fact_keys"):
            value = item.get(key)
            if not isinstance(value, list) or any(not isinstance(v, str) or not v.strip() for v in value):
                blockers.append(_block("CONVICTION_PATH_DEFINITION_INVALID", f"{key} must be an array of nonblank strings", f"{prefix}.{key}"))
            elif len(set(value)) != len(value):
                blockers.append(_block("CONVICTION_PATH_DUPLICATE", f"duplicate {key}", f"{prefix}.{key}"))
            elif any("." in v for v in value):
                blockers.append(_block("CONVICTION_PATH_DEFINITION_INVALID", f"{key} entries must be fact keys without dots", f"{prefix}.{key}"))
        for branch_name in ("when_true", "when_false"):
            branch = item.get(branch_name)
            branch_path = f"{prefix}.{branch_name}"
            if not isinstance(branch, dict) or set(branch) - {"baseline_position", "exclusion_reason"}:
                blockers.append(_block("CONVICTION_PATH_DEFINITION_INVALID", "branch must contain only baseline_position and exclusion_reason", branch_path))
                continue
            position = branch.get("baseline_position")
            if not isinstance(position, str) or position not in _POSITIONS:
                blockers.append(_block("CONVICTION_PATH_DEFINITION_INVALID", "invalid baseline_position", branch_path))
            reason = branch.get("exclusion_reason")
            if position == "excluded":
                if not isinstance(reason, str) or not reason.strip():
                    blockers.append(_block("CONVICTION_PATH_EXCLUSION_REASON_REQUIRED", "excluded branch requires exclusion_reason", branch_path))
                if not isinstance(item.get("contrary_fact_keys"), list) or not item.get("contrary_fact_keys"):
                    blockers.append(_block("CONVICTION_PATH_CONTRARY_REQUIRED", "excluded branch requires contrary_fact_keys", prefix))
            elif reason is not None and not isinstance(reason, str):
                blockers.append(_block("CONVICTION_PATH_DEFINITION_INVALID", "exclusion_reason must be a string", branch_path))
            if position == "candidate" and (not isinstance(item.get("supporting_fact_keys"), list) or not item.get("supporting_fact_keys")):
                blockers.append(_block("CONVICTION_PATH_SUPPORTING_REQUIRED", "candidate branch requires supporting_fact_keys", prefix))
    return blockers


def _raw_id(row: dict[str, Any]) -> str | None:
    if "entityId" in row:
        value = row.get("entityId")
        return value if isinstance(value, str) and value.strip() else None
    value = row.get("id")
    if isinstance(value, str) and value.strip():
        return value
    return None


def _alias(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    try:
        return str(UUID(value)).lower()
    except ValueError:
        return value


def _proof_ids(fact: dict[str, Any], evidence_rows: list[dict[str, Any]]) -> tuple[list[str], list[dict[str, str]]]:
    raw = fact.get("evidenceIds", fact.get("evidence_ids"))
    if not isinstance(raw, list) or not raw:
        return [], [{"code": "INPUT_EVIDENCE_INVALID", "reason": "fact evidenceIds must be a non-empty array"}]
    index: dict[str, list[dict[str, Any]]] = {}
    for evidence in evidence_rows:
        identity = _raw_id(evidence) if isinstance(evidence, dict) else None
        if not identity:
            continue
        aliases = [identity]
        if evidence.get("entityId") is not None:
            aliases.append(evidence.get("entityId"))
        if evidence.get("id") is not None:
            aliases.append(evidence.get("id"))
        seen_aliases: set[str] = set()
        for alias in aliases:
            key = _alias(alias)
            if key in seen_aliases:
                continue
            seen_aliases.add(key)
            if key:
                index.setdefault(key, []).append(evidence)
    output: list[str] = []
    blockers: list[dict[str, str]] = []
    for value in raw:
        key = _alias(value)
        matches = index.get(key, []) if key else []
        if len(matches) != 1:
            blockers.append({"code": "INPUT_EVIDENCE_AMBIGUOUS" if matches else "INPUT_EVIDENCE_INVALID",
                             "reason": str(value)})
            continue
        evidence = matches[0]
        if evidence.get("verificationStatus") != "confirmed":
            blockers.append({"code": "INPUT_UNCONFIRMED", "reason": str(value)})
            continue
        identity = _raw_id(evidence)
        if identity and identity not in output:
            output.append(identity)
    return output, blockers


def execute_candidate_paths(rule: dict[str, Any], snapshot: dict[str, Any],
                            input_validator: Any, fired: bool, point: str = "as_of",
                            predicate_blockers: list[dict[str, Any]] | None = None,
                            coverage_keys: set[str] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Execute only paths explicitly declared by ``rule.outcome``."""
    outcome = rule.get("outcome") if isinstance(rule, dict) else None
    definitions = _definitions(outcome)
    if definitions is _MISSING:
        return [], []
    blockers = validate_candidate_path_definitions(outcome)
    entities = snapshot.get("entities") if isinstance(snapshot, dict) else {}
    actors = entities.get("actors") if isinstance(entities, dict) else None
    actor_rows = actors if isinstance(actors, list) else []
    actor_index: dict[str, list[tuple[str, dict[str, Any], int]]] = {}
    actor_invalid = False
    for actor_index_number, actor in enumerate(actor_rows):
        if not isinstance(actor, dict):
            continue
        identity = _raw_id(actor)
        if identity:
            actor_index.setdefault(_alias(identity), []).append((identity, actor, actor_index_number))
            if actor.get("entityId") and actor.get("id"):
                actor_index.setdefault(_alias(actor["entityId"]), []).append((identity, actor, actor_index_number))
                actor_index.setdefault(_alias(actor["id"]), []).append((identity, actor, actor_index_number))
        elif "entityId" in actor:
            actor_invalid = True
    if actor_invalid:
        blockers.append(_block("CONVICTION_PATH_ACTOR_INVALID", "actor identity is missing or invalid", "entities.actors"))
    facts = snapshot.get("items") if isinstance(snapshot, dict) else []
    facts = facts if isinstance(facts, list) else []
    fact_index: dict[str, list[dict[str, Any]]] = {}
    evidence_rows = entities.get("evidence") if isinstance(entities, dict) else []
    evidence_rows = evidence_rows if isinstance(evidence_rows, list) else []
    for fact in facts:
        if isinstance(fact, dict) and isinstance(fact.get("key"), str):
            fact_index.setdefault(fact["key"], []).append(fact)
    rows: list[dict[str, Any]] = []
    all_blockers = list(blockers)
    for item in definitions if isinstance(definitions, list) else []:
        if not isinstance(item, dict):
            continue
        path_id = item.get("path_id") if isinstance(item, dict) else "<invalid>"
        prefix = f"outcome.candidate_paths[{path_id}]"
        local = list(blockers)
        charge_key = item.get("charge_key")
        if coverage_keys is not None and (not isinstance(charge_key, str) or charge_key not in coverage_keys):
            local.append(_block("CHARGE_OUT_OF_COVERAGE", "declared candidate path charge is outside approved coverage", prefix))
            all_blockers.extend(local)
            continue
        if not isinstance(rule.get("sourceIds"), list) or not rule.get("sourceIds"):
            local.append(_block("CONVICTION_PATH_LEGAL_SOURCE_MISSING", "declared path requires approved legal source ids", prefix))
        actor_key = item.get("actor_fact_key")
        actor_facts = fact_index.get(actor_key, []) if isinstance(actor_key, str) else []
        actor_id: str | None = None
        actor_row_number: int | None = None
        actor_row: dict[str, Any] | None = None
        if len(actor_facts) != 1:
            local.append(_block("CONVICTION_PATH_ACTOR_FACT_INVALID", "actor_fact_key must resolve to exactly one fact", prefix))
        else:
            actor_fact = actor_facts[0]
            actor_ref = actor_fact.get("actorId", actor_fact.get("actor_id"))
            raw_matches = actor_index.get(_alias(actor_ref), []) if actor_ref is not None else []
            seen_rows: set[int] = set()
            matches: list[tuple[str, dict[str, Any]]] = []
            for identity, actor, row_number in raw_matches:
                if row_number not in seen_rows:
                    seen_rows.add(row_number)
                    matches.append((identity, actor))
            if len(matches) != 1:
                local.append(_block("CONVICTION_PATH_ACTOR_AMBIGUOUS", "actor fact must resolve to exactly one frozen actor", prefix))
            else:
                actor_id, actor_row = matches[0]
                actor_row_number = next((number for identity, row, number in raw_matches
                                         if identity == actor_id and row is actor_row), None)
            if isinstance(actor_key, str):
                local.extend(input_validator.check_path(
                    f"facts.{actor_key}.value", phase="candidate_path", point=point))
        support_ids: list[str] = []
        contrary_ids: list[str] = []
        for role, key_name, output in (("supporting", "supporting_fact_keys", support_ids), ("contrary", "contrary_fact_keys", contrary_ids)):
            for key in item.get(key_name, []) if isinstance(item.get(key_name), list) else []:
                matches = fact_index.get(key, []) if isinstance(key, str) else []
                if len(matches) != 1:
                    local.append(_block("CONVICTION_PATH_FACT_INVALID", f"{role} fact key must resolve to exactly one fact: {key}", prefix))
                    continue
                fact = matches[0]
                if isinstance(key, str):
                    local.extend(input_validator.check_path(
                        f"facts.{key}.value", phase="candidate_path", point=point))
                proof_ids, proof_blockers = _proof_ids(fact, evidence_rows)
                local.extend(proof_blockers)
                for proof_id in proof_ids:
                    if proof_id not in output:
                        output.append(proof_id)
                fact_actor_ref = fact.get("actorId", fact.get("actor_id"))
                if actor_id and fact_actor_ref is not None:
                    fact_matches = actor_index.get(_alias(fact_actor_ref), [])
                    fact_rows: set[int] = {number for _, _, number in fact_matches}
                    if len(fact_rows) != 1 or actor_row_number not in fact_rows:
                        local.append(_block("CONVICTION_PATH_ACTOR_MISMATCH", f"{role} fact belongs to another actor: {key}", prefix))
        branch = item.get("when_true" if fired else "when_false") if isinstance(item, dict) else {}
        predicate_invalid = bool(predicate_blockers)
        if predicate_invalid:
            local.extend(predicate_blockers or [])
        branch_ok = not local
        subjective_conflict = bool(item.get("subjective")) and bool(contrary_ids)
        if subjective_conflict:
            local.append(_block("CONVICTION_PATH_CONFLICT", "subjective path has contrary proof", prefix))
            branch_ok = False
        position = branch.get("baseline_position") if branch_ok and isinstance(branch, dict) else None
        reason = branch.get("exclusion_reason") if branch_ok and isinstance(branch, dict) else None
        row = {"id": f"{rule.get('ruleId')}:{rule.get('ruleVersion')}:{point}:{path_id}:{actor_id or 'unknown'}",
               "path_id": path_id, "actor_id": actor_id, "label": item.get("label"),
               "charge_key": item.get("charge_key"), "baseline_position": position,
               "supporting_evidence_ids": support_ids, "contrary_evidence_ids": contrary_ids,
               "legal_source_ids": list(rule.get("sourceIds") or []), "rule_id": rule.get("ruleId"),
               "rule_version": rule.get("ruleVersion"), "point": point,
               "verification_status": "conflicted" if subjective_conflict else "candidate",
               "status": "calculated" if branch_ok else "blocked",
               "exclusion_reason": reason if position == "excluded" else None,
               "blockers": local}
        rows.append(row)
        all_blockers.extend(local)
    return rows, all_blockers
