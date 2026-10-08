"""Pure checks for evidence kinds declared by an applicable rule.

This helper only checks the rule's declared evidence *kinds*.  It does not
decide whether a document, source, or fact is legally sufficient.  Callers
should invoke it after a rule has fired and been deemed applicable; a rule
which did not match must not acquire an evidence blocker from this module.

FactsVersion uses ``entities.evidence[].type`` for the kind,
``verificationStatus == "confirmed"`` for the verified state, and
``entityId`` as its canonical identity.  ``id`` is accepted as the legacy
external alias when a canonical identity is absent or malformed.
"""
from __future__ import annotations

from typing import Any


def _blocker(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def _rule_id(rule: Any) -> str:
    if not isinstance(rule, dict):
        return "<invalid>"
    value = rule.get("ruleId", rule.get("rule_id"))
    return str(value) if value is not None else "<unknown>"


def _required_kinds(rule: Any, rule_id: str,
                    blockers: list[dict[str, str]]) -> list[str]:
    if not isinstance(rule, dict):
        blockers.append(_blocker(
            "RULE_EVIDENCE_REQUIREMENTS_INVALID",
            f"{rule_id}.requiredEvidenceKinds",
            "rule must be an object",
        ))
        return []
    raw = rule.get("requiredEvidenceKinds", rule.get("required_evidence_kinds", []))
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        blockers.append(_blocker(
            "RULE_EVIDENCE_REQUIREMENTS_INVALID",
            f"{rule_id}.requiredEvidenceKinds",
            "required evidence kinds must be a list",
        ))
        return []
    kinds: list[str] = []
    for index, kind in enumerate(raw):
        if not isinstance(kind, str) or not kind.strip():
            blockers.append(_blocker(
                "RULE_EVIDENCE_REQUIREMENT_INVALID",
                f"{rule_id}.requiredEvidenceKinds[{index}]",
                "each required evidence kind must be a non-empty string",
            ))
            continue
        # Preserve exact corpus spelling and order while avoiding duplicate
        # checks for a repeated declaration.
        if kind not in kinds:
            kinds.append(kind)
    return kinds


def _evidence_identity(item: dict[str, Any]) -> str | None:
    for key in ("entityId", "id"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def check_required_evidence(rule: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    """Check confirmed evidence for each kind declared by ``rule``.

    The return value is deterministic and never raises for malformed input.
    Camel-case keys are the only public contract::

        {
            "ruleId": str,
            "requiredKinds": list[str],
            "matchedEvidenceIds": {kind: [identity, ...]},
            "missingKinds": list[str],
            "unconfirmedKinds": list[str],
            "blockers": list[dict[str, str]],
        }

    A kind is satisfied only by an evidence item whose ``type`` matches
    exactly, whose identity is a non-empty ``entityId`` or legacy ``id``,
    and whose ``verificationStatus`` is exactly ``"confirmed"``.  A rule
    with no declared kinds returns no evidence blocker, even when the
    snapshot has no evidence container.
    """
    rule_id = _rule_id(rule)
    blockers: list[dict[str, str]] = []
    required = _required_kinds(rule, rule_id, blockers)
    matched = {kind: [] for kind in required}
    missing: list[str] = []
    unconfirmed: list[str] = []
    evidence_path = f"{rule_id}.entities.evidence"

    if not required:
        return {"ruleId": rule_id, "requiredKinds": required,
                "matchedEvidenceIds": matched, "missingKinds": missing,
                "unconfirmedKinds": unconfirmed, "blockers": blockers}

    evidence: Any = None
    if isinstance(snapshot, dict):
        entities = snapshot.get("entities")
        if isinstance(entities, dict):
            evidence = entities.get("evidence")
        else:
            blockers.append(_blocker(
                "RULE_EVIDENCE_CONTAINER_INVALID",
                evidence_path,
                "snapshot.entities must be an object",
            ))
    else:
        blockers.append(_blocker(
            "RULE_EVIDENCE_CONTAINER_INVALID",
            evidence_path,
            "snapshot must be an object",
        ))

    if evidence is None:
        evidence = []
    elif not isinstance(evidence, list):
        blockers.append(_blocker(
            "RULE_EVIDENCE_CONTAINER_INVALID",
            evidence_path,
            "snapshot.entities.evidence must be a list",
        ))
        evidence = []

    seen_kinds: dict[str, bool] = {kind: False for kind in required}
    for index, item in enumerate(evidence):
        if not isinstance(item, dict):
            blockers.append(_blocker(
                "RULE_EVIDENCE_ITEM_INVALID",
                f"{evidence_path}[{index}]",
                "each evidence item must be an object",
            ))
            continue
        kind = item.get("type")
        if not isinstance(kind, str) or not kind.strip():
            blockers.append(_blocker(
                "RULE_EVIDENCE_ITEM_INVALID",
                f"{evidence_path}[{index}].type",
                "evidence type must be a non-empty string",
            ))
            continue
        if kind not in seen_kinds:
            continue
        seen_kinds[kind] = True
        identity = _evidence_identity(item)
        if identity is None:
            blockers.append(_blocker(
                "RULE_EVIDENCE_IDENTITY_INVALID",
                f"{evidence_path}[{index}]",
                "matched evidence must have a non-empty entityId or id",
            ))
            continue
        if item.get("verificationStatus") == "confirmed":
            if identity not in matched[kind]:
                matched[kind].append(identity)

    for kind in required:
        if matched[kind]:
            continue
        if seen_kinds[kind]:
            unconfirmed.append(kind)
            blockers.append(_blocker(
                "RULE_EVIDENCE_UNCONFIRMED",
                evidence_path,
                f"required evidence kind {kind!r} has no confirmed item with a valid identity",
            ))
        else:
            missing.append(kind)
            blockers.append(_blocker(
                "RULE_EVIDENCE_MISSING",
                evidence_path,
                f"required evidence kind {kind!r} is missing",
            ))

    return {"ruleId": rule_id, "requiredKinds": required,
            "matchedEvidenceIds": matched, "missingKinds": missing,
            "unconfirmedKinds": unconfirmed, "blockers": blockers}
