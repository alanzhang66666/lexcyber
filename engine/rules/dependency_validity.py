"""Registry dependency verification and invalidation-event access."""
from __future__ import annotations

import re
from typing import Any
from uuid import UUID

GLOBAL_BARRIER_KEY = 5495895966559126866
_SIGNED_MIN = -(1 << 63)
_SIGNED_MAX = (1 << 63) - 1
_SIGNED_DECIMAL = re.compile(r"^-?[0-9]+$")
_KINDS = {"rule", "legal_source", "template"}


def validate_dependency_request(payload: Any) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    if not isinstance(payload, dict) or set(payload) != {"coordination", "dependencies"}:
        return None, [{"code": "INVALID_REGISTRY_DEPENDENCIES", "reason": "body must be an object"}]
    coordination = payload.get("coordination")
    deps = payload.get("dependencies")
    if not isinstance(coordination, dict) or set(coordination) != {"backendPid", "challenge"} or not isinstance(deps, list) or len(deps) > 4096:
        return None, [{"code": "INVALID_REGISTRY_DEPENDENCIES", "reason": "coordination and dependencies are required"}]
    pid, challenge = coordination.get("backendPid"), coordination.get("challenge")
    if (not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0 or
            not isinstance(challenge, str) or not _SIGNED_DECIMAL.fullmatch(challenge)):
        return None, [{"code": "INVALID_REGISTRY_DEPENDENCIES", "reason": "invalid coordination"}]
    try:
        challenge_value = int(challenge)
    except ValueError:
        challenge_value = _SIGNED_MAX + 1
    if not _SIGNED_MIN <= challenge_value <= _SIGNED_MAX or challenge_value == GLOBAL_BARRIER_KEY:
        return None, [{"code": "INVALID_REGISTRY_DEPENDENCIES", "reason": "challenge must be a signed 64-bit decimal distinct from global barrier"}]
    result: list[dict[str, str]] = []
    for item in deps:
        if not isinstance(item, dict) or set(item) != {"kind", "key", "version"}:
            result.append({"code": "INVALID_REGISTRY_DEPENDENCIES", "reason": "dependency shape is invalid"})
            continue
        if (not isinstance(item.get("kind"), str) or item.get("kind") not in _KINDS or
                not isinstance(item.get("key"), str) or not isinstance(item.get("version"), str)):
            result.append({"code": "INVALID_REGISTRY_DEPENDENCIES", "reason": "dependency kind/key/version is invalid"})
            continue
    return {"backendPid": pid, "challenge": challenge, "dependencies": deps}, result


def verify_coordination(conn: Any, backend_pid: int, challenge: str) -> bool:
    try:
        challenge_value = int(challenge)
    except (TypeError, ValueError):
        return False
    if not _SIGNED_MIN <= challenge_value <= _SIGNED_MAX or challenge_value == GLOBAL_BARRIER_KEY:
        return False
    row = conn.execute("""
        SELECT 1 FROM pg_locks l
        JOIN pg_database d ON d.oid = l.database
        WHERE l.pid = %s AND l.locktype = 'advisory' AND l.mode = 'ShareLock'
          AND l.classid = ((%s::bigint >> 32) & 4294967295)::oid
          AND l.objid = (%s::bigint & 4294967295)::oid
          AND l.objsubid = 1 AND l.granted
          AND d.oid = (SELECT oid FROM pg_database WHERE datname = current_database())
          AND EXISTS (SELECT 1 FROM pg_locks g
                      JOIN pg_database gd ON gd.oid = g.database
                      WHERE g.pid = l.pid AND g.locktype = 'advisory' AND g.mode = 'ShareLock'
                        AND g.classid = ((%s::bigint >> 32) & 4294967295)::oid
                        AND g.objid = (%s::bigint & 4294967295)::oid AND g.objsubid = 1
                        AND g.granted AND gd.oid = d.oid)
        LIMIT 1
    """, (backend_pid, challenge_value, challenge_value, GLOBAL_BARRIER_KEY, GLOBAL_BARRIER_KEY)).fetchone()
    return row is not None


def verify_dependencies(conn: Any, dependencies: list[dict[str, str]]) -> list[dict[str, str]]:
    invalid: list[dict[str, str]] = []
    queries = {
        "rule": "SELECT 1 FROM engine.effective_rule_package WHERE rule_id = %s AND rule_version = %s LIMIT 1",
        "legal_source": "SELECT 1 FROM engine.effective_legal_source WHERE source_id = %s::uuid AND source_version = %s LIMIT 1",
        "template": "SELECT 1 FROM engine.effective_template_package WHERE template_id = %s AND template_version = %s LIMIT 1",
    }
    for dep in dependencies:
        if dep["kind"] == "legal_source":
            try:
                UUID(dep["key"])
            except (ValueError, AttributeError):
                invalid.append({**dep, "reason": "legal_source key must be a UUID"})
                continue
        found = conn.execute(queries[dep["kind"]], (dep["key"], dep["version"])).fetchone()
        if found is None:
            invalid.append({**dep, "reason": "dependency is not an effective approved exact version"})
    return invalid
