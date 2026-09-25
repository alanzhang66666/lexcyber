from engine.competition_runner import CompetitionAnalysisRunner


def test_model_json_parser_accepts_markdown_fence() -> None:
    payload = CompetitionAnalysisRunner._parse_json('```json\n{"summary":"ok"}\n```')
    assert payload == {"summary": "ok"}


def test_invalid_source_refs_are_reported() -> None:
    runner = CompetitionAnalysisRunner()
    analysis = {"source_refs": ["known", "forged"], "candidate_paths": []}
    retrieval = {"documents": [{"id": "known"}]}
    assert runner._invalid_source_refs(analysis, retrieval) == ["forged"]


def test_invalid_source_refs_inside_candidate_path_are_reported() -> None:
    runner = CompetitionAnalysisRunner()
    analysis = {"candidate_paths": [{"legal_source_ids": ["known", "forged"]}]}
    retrieval = {"documents": [{"id": "known"}]}
    assert runner._invalid_source_refs(analysis, retrieval) == ["forged"]
