from typing import Any, Literal

from pydantic import BaseModel, Field

from skill_runtime.errors import SkillNeedHumanError, SkillPermissionError, SkillProhibitedError
from skill_runtime.schemas import SkillManifest, SkillRequest

KNOWN_PERMISSIONS = {
    "case:read",
    "case:write",
    "document:read",
    "document:write",
    "evidence:read",
    "evidence:write",
    "legal_source:search",
    "model:invoke",
    "network:access",
    "code:execute",
    "human_review:create",
}

DEFAULT_AGENT_PERMISSIONS = [
    "case:read",
    "document:read",
    "evidence:read",
    "legal_source:search",
    "network:access",
    "human_review:create",
]

HIGH_RISK_ACTIONS = {
    "legal.conclusion",
    "legal.liability",
    "legal.crime",
    "legal.deadline.final",
    "legal.outcome.predict",
    "legal.filing.submit",
    "legal.opinion.send",
}


class PolicyDecision(BaseModel):
    allowed: bool
    status: Literal["allow", "denied", "need_human"] = "allow"
    reasons: list[str] = Field(default_factory=list)
    permission_result: str = "granted"
    requires_reviewer: bool = False
    human_approval_required: bool = False


def _granted(request: SkillRequest) -> set[str]:
    if request.granted_permissions is None:
        return set(DEFAULT_AGENT_PERMISSIONS)
    granted = set(request.granted_permissions)
    extra = request.metadata.get("granted_permissions")
    if isinstance(extra, list):
        granted.update(str(item) for item in extra)
    return granted


def evaluate(manifest: SkillManifest, request: SkillRequest) -> PolicyDecision:
    reasons: list[str] = []
    if not manifest.enabled or manifest.status == "disabled":
        return PolicyDecision(allowed=False, status="denied", reasons=["skill is disabled"], permission_result="disabled")
    if manifest.status == "deprecated":
        reasons.append("skill version is deprecated")
    if manifest.risk_level == "prohibited":
        raise SkillProhibitedError(f"skill is prohibited from automatic execution: {manifest.id}")

    missing = [permission for permission in manifest.permission_list() if permission not in _granted(request)]
    if missing:
        raise SkillPermissionError(f"missing permissions: {', '.join(missing)}")

    jurisdiction = request.input.get("jurisdiction") or request.metadata.get("jurisdiction")
    if manifest.category.startswith("legal.") and not jurisdiction:
        reasons.append("jurisdiction is not set; defaulting to caller metadata")

    if "code:execute" in manifest.permission_list():
        raise SkillProhibitedError("code execution skills are not enabled in v0.2")

    if manifest.risk_level == "high" and not request.human_approved:
        raise SkillNeedHumanError(f"high-risk skill requires human approval: {manifest.id}")

    decision = PolicyDecision(
        allowed=True,
        reasons=reasons,
        permission_result="granted",
        requires_reviewer=manifest.risk_level in {"medium", "high"},
        human_approval_required=manifest.risk_level == "high",
    )
    return decision


def check_task_budget(state: dict[str, Any], extra_calls: int = 1) -> None:
    budget = int((state.get("metadata") or {}).get("skill_budget", 20))
    used = len(state.get("skill_results", [])) + len(state.get("skill_errors", []))
    if used + extra_calls > budget:
        raise SkillPermissionError("skill execution budget exceeded")
