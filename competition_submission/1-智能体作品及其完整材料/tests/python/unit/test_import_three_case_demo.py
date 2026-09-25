from pathlib import Path

import pytest

from scripts.import_three_case_demo import (
    extract_candidates_from_parse_content,
    find_material,
    list_case_materials,
    preflight_materials,
    resolve_material,
)


def test_list_case_materials_only_includes_input_case_material():
    rows = list_case_materials()
    assert {code for code, _document_id, _entry in rows} == {"A", "B", "C"}
    entries = [entry for _code, _document_id, entry in rows]
    assert all("法学标注" not in entry for entry in entries)
    assert any(entry.endswith("合成案例011（改）-输入材料.docx") for entry in entries)


def test_find_material_matches_archive_filename(tmp_path: Path):
    nested = tmp_path / "演示案例A"
    nested.mkdir()
    target = nested / "合成案例011（改）-输入材料.docx"
    target.write_bytes(b"docx")
    found = find_material(tmp_path, "演示案例A/合成案例011（改）-输入材料.docx")
    assert found == target


def test_resolve_material_is_fail_closed_without_placeholder(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="missing material"):
        resolve_material(tmp_path, "missing.docx", allow_placeholder=False)


def test_resolve_material_placeholder_is_opt_in(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    smoke = tmp_path / "smoke.docx"
    smoke.write_bytes(b"pk")
    monkeypatch.setattr("scripts.import_three_case_demo.PLACEHOLDER", smoke)
    source, placeholder = resolve_material(None, "missing.docx", allow_placeholder=True)
    assert source == smoke
    assert placeholder is True


def test_preflight_fails_closed_when_docs_dir_missing():
    with pytest.raises(SystemExit, match="missing case_material"):
        preflight_materials(None, allow_placeholder=False)


def test_preflight_allows_placeholder_only_when_opted_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    smoke = tmp_path / "smoke.docx"
    smoke.write_bytes(b"pk")
    monkeypatch.setattr("scripts.import_three_case_demo.PLACEHOLDER", smoke)
    preflight_materials(None, allow_placeholder=True)


def test_extract_candidates_from_parse_content_maps_paragraph_locators():
    items = extract_candidates_from_parse_content(
        {
            "text": "2023年5月12日转入人民币 12万元。",
            "paragraphs": [
                {
                    "paragraph": 2,
                    "text": "2023年5月12日转入人民币 12万元。",
                    "locator": "paragraph:2",
                }
            ],
        }
    )
    assert items == [
        {"kind": "date", "value": "2023年5月12日", "locator": "paragraph:2"},
        {"kind": "amount", "value": "人民币 12万元", "locator": "paragraph:2"},
    ]

