from agents.reviewer.agent import ReviewerAgent
from agents.supervisor.agent import SupervisorAgent


def test_supervisor_is_domain_neutral():
    plan = SupervisorAgent().plan("extract and summarize")
    assert plan.steps == ["worker", "tool", "reviewer"]
    assert plan.needs_retrieval is True


def test_reviewer_minimal_contract():
    reviewer = ReviewerAgent()
    assert reviewer.review("query", "candidate", 0) == "PASS"
    assert reviewer.review("query", "", 0) == "RETRY"
    assert reviewer.review("", "candidate", 0) == "NEED_HUMAN"
