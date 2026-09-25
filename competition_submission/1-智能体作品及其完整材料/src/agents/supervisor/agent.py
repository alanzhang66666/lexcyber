from dataclasses import dataclass
from typing import Any

from skill_runtime.policy import DEFAULT_AGENT_PERMISSIONS
from skill_runtime.router import SkillRouter
from skill_runtime.schemas import SkillRequest


@dataclass
class Plan:
    goal: str
    steps: list[dict[str, Any]]
    risk_level: str = "low"
    requires_human_review: bool = False
    needs_retrieval: bool = False


HIGH_RISK_HINTS = ("定罪", "罪名", "责任认定", "胜率", "诉讼时效", "上诉期限", "提交法院", "正式意见")


class SupervisorAgent:
    def __init__(self, router: SkillRouter | None = None):
        self.router = router or SkillRouter()

    def plan(self, user_query: str, context: dict[str, Any] | None = None) -> Plan:
        context = context or {}
        requests = self.router.build_requests(user_query, context, granted_permissions=DEFAULT_AGENT_PERMISSIONS)
        steps = [
            {"step_id": str(index), "skill_id": request.skill_id, "inputs": request.input, "depends_on": [str(index - 1)] if index > 1 else []}
            for index, request in enumerate(requests, start=1)
        ]
        risk_level = "high" if any(hint in user_query for hint in HIGH_RISK_HINTS) else "low"
        if any(request.skill_id.startswith("legal.review") or request.skill_id.endswith("contradiction.detect") for request in requests):
            if risk_level == "low":
                risk_level = "medium"
        return Plan(
            goal=user_query[:200] or "process legal materials",
            steps=steps,
            risk_level=risk_level,
            requires_human_review=risk_level == "high",
            needs_retrieval=any(request.skill_id.startswith("legal.source") or request.skill_id.endswith("verify") for request in requests),
        )

    def to_skill_requests(self, plan: Plan, context: dict[str, Any]) -> list[SkillRequest]:
        requests = []
        for step in plan.steps:
            requests.append(
                SkillRequest(
                    skill_id=step["skill_id"],
                    input=step.get("inputs") or {},
                    metadata={"step_id": step["step_id"], **context},
                    actor=str(context.get("actor", "agent")),
                    case_id=context.get("case_id"),
                    request_id=context.get("request_id"),
                    granted_permissions=DEFAULT_AGENT_PERMISSIONS,
                    human_approved=bool(context.get("human_approved")),
                )
            )
        return requests
