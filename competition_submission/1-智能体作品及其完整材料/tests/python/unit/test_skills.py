from skill_runtime.executor import SkillExecutor
from skill_runtime.schemas import SkillRequest
from skills.legal.handlers import document_redact, timeline_build


def test_redaction_and_timeline_are_traceable():
    redacted = document_redact({"text": "联系方式 13812345678，邮箱 test@example.com"})
    assert "13812345678" not in redacted["text"]
    timeline = timeline_build({"events": [{"date": "2024-02-01", "description": "B"}, {"date": "2024-01-01", "description": "A"}]})
    assert [event["description"] for event in timeline["events"]] == ["A", "B"]


def test_english_party_and_citation_compat():
    parties = SkillExecutor().execute(SkillRequest(skill_id="legal.party.extract", input={"text": "Plaintiff: Acme Ltd\nDefendant: Beta LLC"}))
    assert parties.status == "completed"
    roles = {item["role"].lower() for item in parties.output["parties"]}
    assert "plaintiff" in roles
    citations = SkillExecutor().execute(SkillRequest(skill_id="legal.citation.parse", input={"text": "See Article 509 of Civil Code"}))
    assert citations.output["citations"][0]["article"] == "509"


def test_authority_rank_and_effective_date():
    sources = [
        {"id": "a", "metadata": {"source_authority": "case", "title": "case", "effective_from": "2020-01-01", "effective_to": "2020-12-31"}},
        {"id": "b", "metadata": {"source_authority": "law", "title": "law", "effective_from": "2021-01-01"}},
    ]
    ranked = SkillExecutor().execute(SkillRequest(skill_id="legal.source.authority.rank", input={"sources": sources}))
    assert ranked.output["sources"][0]["source_authority"] == "law"
    checked = SkillExecutor().execute(SkillRequest(skill_id="legal.source.effective_date.check", input={"sources": sources, "as_of_date": "2026-01-01"}))
    by_id = {item["source_id"]: item for item in checked.output["results"]}
    assert by_id["a"]["effective"] is False
    assert by_id["b"]["effective"] is True


def test_human_gate_for_high_risk_query():
    result = SkillExecutor().execute(SkillRequest(skill_id="legal.review.human_gate", input={"text": "请给出罪名和责任认定", "risk_level": "low"}))
    assert result.output["need_human"] is True
    assert result.output["risk_level"] == "high"
