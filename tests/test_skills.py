from skill_runtime.executor import SkillExecutor
from skill_runtime.schemas import SkillRequest
from skills.legal.handlers import document_redact, timeline_build


def test_legal_skill_catalog_is_registered():
    skills = SkillExecutor().list_skills()
    ids = {skill["id"] for skill in skills}
    assert "legal.document.classify" in ids
    assert "legal.citation.verify" in ids
    assert len(ids) == 10


def test_executor_runs_registered_skill():
    result = SkillExecutor().execute(SkillRequest(skill_id="legal.citation.parse", input={"text": "依据《民法典》第五百零九条"}))
    assert result.status == "completed"
    assert result.output["citations"][0]["title"] == "民法典"


def test_redaction_and_timeline_are_traceable():
    redacted = document_redact({"text": "联系方式 13812345678，邮箱 test@example.com"})
    assert "13812345678" not in redacted["text"]
    timeline = timeline_build({"events": [{"date": "2024-02-01", "description": "B"}, {"date": "2024-01-01", "description": "A"}]})
    assert [event["description"] for event in timeline["events"]] == ["A", "B"]
