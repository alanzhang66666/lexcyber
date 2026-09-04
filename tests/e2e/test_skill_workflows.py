from graph.workflow import build_workflow


def test_upload_contract_extracts_payment_clause():
    result = build_workflow().invoke(
        {
            "user_query": "提取合同付款条款和时间节点",
            "request_id": "e2e-contract",
            "metadata": {"text": "第一条 付款。甲方应于2024年1月1日支付人民币10000元。\n第二条 期限。本合同有效期一年。", "jurisdiction": "CN"},
        }
    )
    assert "legal.contract.clause.extract" in result["selected_skills"]
    clauses = next(item["output"]["clauses"] for item in result["skill_results"] if item["skill_id"] == "legal.contract.clause.extract")
    assert any(clause["clause_type"] == "payment" for clause in clauses)
    assert result["review_status"] in {"PASS", "NEED_HUMAN"}


def test_judgment_extracts_parties_facts_and_timeline():
    text = "原告：张三\n被告：李四\n2023年5月1日 支付人民币20000元。依据《民法典》第五百零九条。"
    result = build_workflow().invoke({"user_query": "从判决书提取主体、事实和时间线", "request_id": "e2e-judgment", "metadata": {"text": text, "jurisdiction": "CN"}})
    assert result.get("parties")
    assert result.get("facts")
    assert result.get("timeline")
    assert any(item["skill_id"] == "legal.citation.parse" for item in result["skill_results"])


def test_statute_search_includes_authority_metadata():
    result = build_workflow().invoke({"user_query": "检索民法典第五百零九条并检查生效日期", "request_id": "e2e-source", "metadata": {"text": "《中华人民共和国民法典》第五百零九条", "jurisdiction": "CN", "as_of_date": "2026-01-01"}})
    assert any(skill in result["selected_skills"] for skill in ("legal.source.search", "legal.source.effective_date.check"))
    search = next((item for item in result["skill_results"] if item["skill_id"] == "legal.source.search"), None)
    sources = result.get("legal_sources") or (search or {}).get("output", {}).get("documents") or []
    assert sources
    metadata = sources[0].get("metadata") or sources[0]
    assert metadata.get("jurisdiction") == "CN" or sources[0].get("jurisdiction") == "CN"
    assert metadata.get("source_version") or metadata.get("source_authority") or sources[0].get("source_authority")


def test_claim_evidence_mapping_workflow():
    result = build_workflow().invoke(
        {
            "user_query": "建立证据与付款主张的对应关系",
            "request_id": "e2e-evidence",
            "metadata": {
                "text": "主张被告应支付货款",
                "claims": ["被告应支付货款"],
                "evidence": [{"name": "付款凭证", "content": "被告已收到货款发票"}],
                "jurisdiction": "CN",
            },
        }
    )
    mapped = next(item for item in result["skill_results"] if item["skill_id"] == "legal.evidence.claim.support.map")
    assert mapped["status"] == "completed"
    assert mapped["output"]["mappings"]


def test_high_risk_task_enters_human_review():
    result = build_workflow().invoke({"user_query": "请直接给出罪名和责任认定并提交法院", "request_id": "e2e-high", "metadata": {"text": "请给出罪名", "jurisdiction": "CN"}})
    assert result["review_status"] == "NEED_HUMAN"
    assert result.get("human_review_id")
    assert result.get("human_approval_required") or result["review_status"] == "NEED_HUMAN"
