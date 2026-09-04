import re

from retrieval.schemas import RetrievedDocument

SAMPLE_SOURCES = [
    RetrievedDocument(
        id="cn-civil-code-509",
        content="当事人应当按照约定全面履行自己的义务。《中华人民共和国民法典》第五百零九条。",
        score=0.92,
        metadata={
            "jurisdiction": "CN",
            "source_authority": "law",
            "title": "中华人民共和国民法典",
            "article": "第五百零九条",
            "article_number": "509",
            "effective_from": "2021-01-01",
            "effective_to": None,
            "source_version": "2021-01-01",
            "source_url": "local://corpus/cn-civil-code-509",
        },
    ),
    RetrievedDocument(
        id="cn-civil-procedure-64",
        content="当事人对自己提出的主张，有责任提供证据。《中华人民共和国民事诉讼法》第六十四条。",
        score=0.88,
        metadata={
            "jurisdiction": "CN",
            "source_authority": "law",
            "title": "中华人民共和国民事诉讼法",
            "article": "第六十四条",
            "article_number": "64",
            "effective_from": "2024-01-01",
            "effective_to": None,
            "source_version": "2024-01-01",
            "source_url": "local://corpus/cn-civil-procedure-64",
        },
    ),
    RetrievedDocument(
        id="cn-contract-law-repealed",
        content="《中华人民共和国合同法》已废止，相关规则并入民法典。",
        score=0.4,
        metadata={
            "jurisdiction": "CN",
            "source_authority": "law",
            "title": "中华人民共和国合同法",
            "article": "第一条",
            "effective_from": "1999-10-01",
            "effective_to": "2020-12-31",
            "source_version": "1999-10-01",
            "source_url": "local://corpus/cn-contract-law-repealed",
        },
    ),
]


def search_corpus(query: str, top_k: int = 5) -> list[RetrievedDocument]:
    query_lower = query.lower()
    parts = [part for part in re.split(r"[\s,，。、《》第条款项目]+", query_lower) if len(part) >= 2]
    scored: list[RetrievedDocument] = []
    for document in SAMPLE_SOURCES:
        metadata = document.metadata or {}
        haystack = f"{document.content} {metadata}".lower()
        title = str(metadata.get("title") or "").lower()
        article = str(metadata.get("article") or "").lower()
        score = 0.0
        if query_lower in haystack or document.content.lower() in query_lower:
            score = 0.95
        if title and title in query_lower:
            score = max(score, 0.9)
        if article and article in query_lower:
            score = max(score, 0.88)
        if any(alias in query_lower and alias in haystack for alias in ("民法典", "合同法", "民事诉讼法")):
            score = max(score, 0.8)
        hits = sum(part in haystack for part in parts)
        if hits:
            score = max(score, min(0.9, 0.3 + hits * 0.15))
        if score >= 0.3:
            scored.append(document.model_copy(update={"score": score}))
    scored.sort(key=lambda item: item.score, reverse=True)
    return scored[:top_k]
