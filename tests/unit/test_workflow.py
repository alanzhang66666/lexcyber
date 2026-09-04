from agents.reviewer.agent import ReviewerAgent
from agents.supervisor.agent import SupervisorAgent


def test_supervisor_selects_skills_instead_of_hardcoded_nodes():
    plan = SupervisorAgent().plan("提取合同付款条款")
    assert plan.steps
    assert all("skill_id" in step for step in plan.steps)
    assert "legal.contract.clause.extract" in [step["skill_id"] for step in plan.steps]


def test_reviewer_minimal_contract():
    reviewer = ReviewerAgent()
    assert reviewer.review("query", "candidate", 0) == "PASS"
    assert reviewer.review("query", "", 0) == "RETRY"
    assert reviewer.review("", "candidate", 0) == "NEED_HUMAN"


def test_reviewer_routes_human_gate():
    reviewer = ReviewerAgent()
    status = reviewer.review("query", "candidate", 0, {"human_approval_required": True})
    assert status == "NEED_HUMAN"
