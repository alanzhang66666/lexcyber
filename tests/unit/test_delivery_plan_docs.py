"""Structural guards for the iterative delivery and legal sign-off documents.

The tests intentionally use only the standard library plus pytest's normal
assertion collection.  They parse the Markdown tables and headings directly
so document drift produces a focused assertion that names the affected round,
row, or sign-off entry.

Validates: Requirements 1.2, 1.7, 1.8, 1.12, 2.7, 6.2, 6.4, 6.6, 6.7, 6.8, 9.11
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLAN_DOCUMENT = ROOT / "docs" / "archive" / "iterative-delivery-plan.md"
SIGNOFF_DOCUMENT = ROOT / "docs" / "legal-signoff-checklist.md"

ROUND_NAMES = ("R1", "R2", "R3", "R4")
FIXED_ROUND_HEADINGS = ("范围", "入口条件", "出口条件", "产物清单", "负责轨道")
SIGNOFF_IDS = tuple(f"SIGNOFF-{number:03d}" for number in range(1, 6))
TRACK_NAMES = {"T1", "T2", "T3"}
SIGNOFF_STATUSES = {"待签", "已签", "已解禁"}
UNLOCK_ROUNDS = set(ROUND_NAMES) | {"未定"}

ROUND_HEADING = re.compile(r"^## (R[1-4])(?:\s+.*)?$")
SUBHEADING = re.compile(r"^### (.+?)\s*$")
TABLE_SEPARATOR_CELL = re.compile(r"^:?-{3,}:?$")
SIGNOFF_LINK = re.compile(r"\[(SIGNOFF-\d{3})\]\(([^)]+)\)")
SIGNOFF_CELL = re.compile(r"\[(SIGNOFF-\d{3})\]\(#(signoff-\d{3})\)")
TRACK = re.compile(r"(?<![A-Za-z0-9_])T[123](?![A-Za-z0-9_])")
DETAIL_HEADING = re.compile(r"^### (SIGNOFF-\d{3})(?:：|$)", re.MULTILINE)
DETAIL_ANCHOR = re.compile(r"<a id=\"(signoff-\d{3})\"></a>")

SIGNOFF_TABLE_HEADER = (
    "条目标识",
    "待会签内容",
    "负责人",
    "解禁后验收动作",
    "安全门闩位置",
    "默认开关名称",
    "状态",
    "返回码",
    "解禁归属轮次",
)
EXIT_TABLE_HEADER = ("判据", "判定命令或判定产物", "会签")


@dataclass(frozen=True)
class MarkdownTable:
    """A small dependency-free representation of one Markdown table."""

    header: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    header_line: int


@dataclass(frozen=True)
class RoundSection:
    name: str
    lines: tuple[str, ...]


def _read_document(path: Path) -> str:
    assert path.is_file(), f"{path}: expected Markdown document to exist"
    return path.read_text(encoding="utf-8")


def _split_table_row(line: str) -> tuple[str, ...]:
    stripped = line.strip()
    assert stripped.startswith("|") and stripped.endswith("|"), (
        f"expected a pipe-delimited Markdown row, got {line!r}"
    )
    return tuple(cell.strip() for cell in stripped[1:-1].split("|"))


def _is_table_separator(cells: tuple[str, ...]) -> bool:
    return bool(cells) and all(TABLE_SEPARATOR_CELL.fullmatch(cell) for cell in cells)


def _parse_table(lines: list[str], start: int, document: Path) -> MarkdownTable:
    header = _split_table_row(lines[start])
    assert start + 1 < len(lines), f"{document}:{start + 1}: table is missing its separator row"
    separator = _split_table_row(lines[start + 1])
    assert len(separator) == len(header), (
        f"{document}:{start + 2}: table separator has {len(separator)} columns; "
        f"header has {len(header)}"
    )
    assert _is_table_separator(separator), f"{document}:{start + 2}: invalid Markdown table separator"

    rows: list[tuple[str, ...]] = []
    line_number = start + 2
    while line_number < len(lines) and lines[line_number].strip().startswith("|"):
        row = _split_table_row(lines[line_number])
        rows.append(row)
        line_number += 1
    return MarkdownTable(header=header, rows=tuple(rows), header_line=start + 1)


def _find_table(lines: list[str], header: tuple[str, ...], document: Path, start: int = 0) -> MarkdownTable:
    for line_number in range(start, len(lines)):
        if not lines[line_number].strip().startswith("|"):
            continue
        if _split_table_row(lines[line_number]) == header:
            return _parse_table(lines, line_number, document)
    raise AssertionError(f"{document}: expected a Markdown table with header {header!r}")


def _parse_round_sections(text: str) -> dict[str, RoundSection]:
    lines = text.splitlines()
    starts = [
        (line_number, match.group(1))
        for line_number, line in enumerate(lines)
        if (match := ROUND_HEADING.fullmatch(line))
    ]
    assert tuple(name for _, name in starts) == ROUND_NAMES, (
        f"{PLAN_DOCUMENT}: expected round headings {ROUND_NAMES!r}; "
        f"found {tuple(name for _, name in starts)!r}"
    )

    sections: dict[str, RoundSection] = {}
    for position, (start, name) in enumerate(starts):
        end = starts[position + 1][0] if position + 1 < len(starts) else len(lines)
        sections[name] = RoundSection(name=name, lines=tuple(lines[start:end]))
    return sections


def _section_body(section: RoundSection, heading: str) -> tuple[str, ...]:
    heading_line = f"### {heading}"
    try:
        start = section.lines.index(heading_line) + 1
    except ValueError as error:
        raise AssertionError(f"{PLAN_DOCUMENT}: {section.name}: missing heading {heading!r}") from error

    end = len(section.lines)
    for line_number in range(start, len(section.lines)):
        if SUBHEADING.fullmatch(section.lines[line_number]):
            end = line_number
            break
    return section.lines[start:end]


def _plan_signoff_links(text: str) -> list[tuple[str, str]]:
    return SIGNOFF_LINK.findall(text)


def _parse_signoff_entries(text: str) -> MarkdownTable:
    lines = text.splitlines()
    return _find_table(lines, SIGNOFF_TABLE_HEADER, SIGNOFF_DOCUMENT)


STATUS_DOCUMENTS = (
    ("README.md", ROOT / "README.md"),
    ("AGENTS.md", ROOT / "AGENTS.md"),
    ("docs/lexcyber-0.8.zh-CN.md", ROOT / "docs" / "lexcyber-0.8.zh-CN.md"),
    ("docs/lexcyber-0.8.en.md", ROOT / "docs" / "lexcyber-0.8.en.md"),
)
CURRENT_STATE_DATE_MARKER = re.compile(
    r"\*\*(?:现状日期|Current-state date)[:：]\*\*\s+\d{4}-\d{2}-\d{2}\b"
)
CONTRACT_VERSION_MARKER = re.compile(r"\*\*(?:契约版本|Contract version)[:：]\*\*\s+0\.8\.0\b")
PUBLIC_GATE_CODES = (
    "SOURCE_SEARCH_UNAVAILABLE",
    "SENTENCING_UNAVAILABLE",
    "COMPLIANCE_UNAVAILABLE",
    "CONVICTION_UNAVAILABLE",
)
TRACK_STATUS_ROW = re.compile(r"^\|\s*(T[123])\s*\|\s*(.*?)\s*\|$")
BILINGUAL_TRACK_STATUS_MARKERS = {
    "T1": ("已合入 main", "On `main`"),
    "T2": ("已合入本地 main", "Merged into local `main`"),
    "T3": ("内部能力已落地", "Internal capability is in place"),
}
STALE_CASE_IMPORT_STATUS = re.compile(
    r"(?:"
    r"(?:仍在|位于|处于|待合入|未合入|尚未合入|尚待合入|remain(?:ing)? on|still on|pending merge|not merged|awaiting merge)"
    r"[^\n]*feat/case-import"
    r"|feat/case-import[^\n]*(?:仍在|位于|处于|待合入|未合入|尚未合入|尚待合入|remain(?:ing)? on|still on|pending merge|not merged|awaiting merge)"
    r")",
    re.IGNORECASE,
)


def _extract_track_status_rows(text: str, document: Path) -> dict[str, tuple[int, str]]:
    rows: dict[str, tuple[int, str]] = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        match = TRACK_STATUS_ROW.fullmatch(line)
        if not match:
            continue
        track, status = match.groups()
        assert track not in rows, f"{document}: line {line_number}: duplicate status row for {track}"
        rows[track] = (line_number, status)

    expected_tracks = set(BILINGUAL_TRACK_STATUS_MARKERS)
    assert set(rows) == expected_tracks, (
        f"{document}: expected one status row for each track {sorted(expected_tracks)!r}; "
        f"found {sorted(rows)!r}"
    )
    return rows


def test_status_document_set_is_current_and_bilingual_tracks_are_aligned() -> None:
    """Feature: iterative-delivery-plan, status-document alignment guards."""
    documents = {
        label: (path, _read_document(path))
        for label, path in STATUS_DOCUMENTS
    }

    for label, (path, text) in documents.items():
        assert CURRENT_STATE_DATE_MARKER.search(text), (
            f"{path} ({label}): expected a bold current-state date line with an ISO date"
        )
        assert CONTRACT_VERSION_MARKER.search(text), (
            f"{path} ({label}): expected the contract version marker to be exactly 0.8.0"
        )
        assert "501" in text, f"{path} ({label}): expected the public gate status marker 501"
        for error_code in PUBLIC_GATE_CODES:
            assert error_code in text, (
                f"{path} ({label}): expected public 501 error code {error_code}; "
                "the four gated public capabilities must remain documented"
            )

    zh_label = "docs/lexcyber-0.8.zh-CN.md"
    en_label = "docs/lexcyber-0.8.en.md"
    zh_path, zh_text = documents[zh_label]
    en_path, en_text = documents[en_label]
    zh_tracks = _extract_track_status_rows(zh_text, zh_path)
    en_tracks = _extract_track_status_rows(en_text, en_path)

    for track, (zh_marker, en_marker) in BILINGUAL_TRACK_STATUS_MARKERS.items():
        zh_line, zh_status = zh_tracks[track]
        en_line, en_status = en_tracks[track]
        assert zh_marker in zh_status, (
            f"{zh_path}: line {zh_line}: {track} status is not aligned with the current state; "
            f"expected marker {zh_marker!r}, found {zh_status!r}"
        )
        assert en_marker in en_status, (
            f"{en_path}: line {en_line}: {track} status is not aligned with the Chinese document; "
            f"expected marker {en_marker!r}, found {en_status!r}"
        )

    readme_path, readme_text = documents["README.md"]
    assert "feat/case-import" not in readme_text, (
        f"{readme_path}: must not retain the old feat/case-import branch-location status"
    )
    for label, (path, text) in documents.items():
        stale_match = STALE_CASE_IMPORT_STATUS.search(text)
        assert stale_match is None, (
            f"{path} ({label}): found stale case-import branch status {stale_match.group(0)!r}; "
            "use the merged-local-main state instead"
        )


def test_delivery_plan_round_structure_and_exit_conditions() -> None:
    """Feature: iterative-delivery-plan, Property 8: plan structure is consistent."""
    plan_text = _read_document(PLAN_DOCUMENT)
    sections = _parse_round_sections(plan_text)

    plan_links = _plan_signoff_links(plan_text)
    linked_ids = {signoff_id for signoff_id, _ in plan_links}
    assert linked_ids == set(SIGNOFF_IDS), (
        f"{PLAN_DOCUMENT}: expected exactly {SIGNOFF_IDS!r} in Markdown links; "
        f"found {tuple(sorted(linked_ids))!r}"
    )
    for signoff_id, target in plan_links:
        expected_target = f"../legal-signoff-checklist.md#{signoff_id.lower()}"
        assert target == expected_target, (
            f"{PLAN_DOCUMENT}: {signoff_id}: expected link target {expected_target!r}; found {target!r}"
        )

    exit_table_signoff_ids: set[str] = set()
    for round_name in ROUND_NAMES:
        section = sections[round_name]
        headings = tuple(
            match.group(1)
            for line in section.lines
            if (match := SUBHEADING.fullmatch(line))
        )
        assert headings == FIXED_ROUND_HEADINGS, (
            f"{PLAN_DOCUMENT}: {round_name}: expected fixed ### headings "
            f"{FIXED_ROUND_HEADINGS!r}; found {headings!r}"
        )

        track_text = "\n".join(_section_body(section, "负责轨道"))
        tracks = set(TRACK.findall(track_text))
        assert tracks and tracks <= TRACK_NAMES, (
            f"{PLAN_DOCUMENT}: {round_name}: expected non-empty responsible tracks from "
            f"{sorted(TRACK_NAMES)!r}; found {sorted(tracks)!r}"
        )

        assert re.search(r"回滚判据", "\n".join(section.lines)), (
            f"{PLAN_DOCUMENT}: {round_name}: expected a 回滚判据 in the round section"
        )

        exit_lines = list(_section_body(section, "出口条件"))
        exit_table = _find_table(exit_lines, EXIT_TABLE_HEADER, PLAN_DOCUMENT)
        assert len(exit_table.header) == 3, (
            f"{PLAN_DOCUMENT}: {round_name}: exit table at line {exit_table.header_line} "
            f"must have exactly three columns; found {len(exit_table.header)}"
        )
        assert exit_table.rows, f"{PLAN_DOCUMENT}: {round_name}: exit table must contain at least one criterion"

        model_rows = []
        for row_number, row in enumerate(exit_table.rows, start=1):
            assert len(row) == 3, (
                f"{PLAN_DOCUMENT}: {round_name}: exit table row {row_number} must have three columns; "
                f"found {len(row)}"
            )
            assert row[0], f"{PLAN_DOCUMENT}: {round_name}: exit row {row_number} has an empty 判据 cell"
            assert row[1], (
                f"{PLAN_DOCUMENT}: {round_name}: exit row {row_number} has an empty "
                "判定命令或判定产物 cell"
            )
            exit_table_signoff_ids.update(signoff_id for signoff_id, _ in SIGNOFF_LINK.findall(row[2]))
            if "模型链路保留" in row[0]:
                model_rows.append(row)

        assert len(model_rows) == 1, (
            f"{PLAN_DOCUMENT}: {round_name}: expected exactly one 模型链路保留 exit criterion; "
            f"found {len(model_rows)}"
        )

    assert exit_table_signoff_ids == set(SIGNOFF_IDS), (
        f"{PLAN_DOCUMENT}: exit-table sign-off links must cover {SIGNOFF_IDS!r}; "
        f"found {tuple(sorted(exit_table_signoff_ids))!r}"
    )

    signoff_entries = _parse_signoff_entries(_read_document(SIGNOFF_DOCUMENT))
    checklist_ids = {
        match.group(1)
        for row in signoff_entries.rows
        if row
        if (match := SIGNOFF_CELL.fullmatch(row[0]))
    }
    assert checklist_ids == set(SIGNOFF_IDS), (
        f"{SIGNOFF_DOCUMENT}: sign-off IDs must match plan links {SIGNOFF_IDS!r}; "
        f"found {tuple(sorted(checklist_ids))!r}"
    )


def test_legal_signoff_checklist_entries_and_details_are_consistent() -> None:
    """Feature: iterative-delivery-plan, Property 9: sign-off entries are consistent."""
    signoff_text = _read_document(SIGNOFF_DOCUMENT)
    signoff_table = _parse_signoff_entries(signoff_text)

    assert signoff_table.header == SIGNOFF_TABLE_HEADER, (
        f"{SIGNOFF_DOCUMENT}: expected nine-field sign-off table header; "
        f"found {signoff_table.header!r}"
    )
    assert len(signoff_table.rows) == len(SIGNOFF_IDS), (
        f"{SIGNOFF_DOCUMENT}: expected {len(SIGNOFF_IDS)} sign-off rows; "
        f"found {len(signoff_table.rows)}"
    )

    seen_ids: set[str] = set()
    for row_number, row in enumerate(signoff_table.rows, start=1):
        assert len(row) == len(SIGNOFF_TABLE_HEADER), (
            f"{SIGNOFF_DOCUMENT}: sign-off row {row_number} must have "
            f"{len(SIGNOFF_TABLE_HEADER)} columns; found {len(row)}: {row!r}"
        )

        match = SIGNOFF_CELL.fullmatch(row[0])
        assert match, (
            f"{SIGNOFF_DOCUMENT}: sign-off row {row_number} identifier must be a link of the form "
            f"[SIGNOFF-001](#signoff-001); found {row[0]!r}"
        )
        signoff_id, anchor_id = match.groups()
        assert signoff_id in SIGNOFF_IDS, (
            f"{SIGNOFF_DOCUMENT}: sign-off row {row_number} uses unexpected identifier {signoff_id!r}"
        )
        assert anchor_id == signoff_id.lower(), (
            f"{SIGNOFF_DOCUMENT}: {signoff_id}: table anchor must be #{signoff_id.lower()}; "
            f"found #{anchor_id}"
        )
        assert signoff_id not in seen_ids, f"{SIGNOFF_DOCUMENT}: duplicate sign-off identifier {signoff_id}"
        seen_ids.add(signoff_id)

        for column_number, value in enumerate(row[1:], start=2):
            assert value.strip(), (
                f"{SIGNOFF_DOCUMENT}: {signoff_id}: column {column_number} must not be empty; row={row!r}"
            )

        status = row[6].strip()
        assert status in SIGNOFF_STATUSES, (
            f"{SIGNOFF_DOCUMENT}: {signoff_id}: status must be one of {sorted(SIGNOFF_STATUSES)!r}; "
            f"found {status!r}"
        )
        response_code = row[7].strip().strip("`")
        if status == "待签":
            assert response_code == "501", (
                f"{SIGNOFF_DOCUMENT}: {signoff_id}: 待签 entries must retain response code 501; "
                f"found {response_code!r}"
            )
        unlock_round = row[8].strip()
        assert unlock_round in UNLOCK_ROUNDS, (
            f"{SIGNOFF_DOCUMENT}: {signoff_id}: unlock round must be one of "
            f"{sorted(UNLOCK_ROUNDS)!r}; found {unlock_round!r}"
        )
        if status in {"已签", "已解禁"}:
            assert unlock_round in ROUND_NAMES, (
                f"{SIGNOFF_DOCUMENT}: {signoff_id}: signed entries must have a concrete unlock round; "
                f"found {unlock_round!r}"
            )

    assert seen_ids == set(SIGNOFF_IDS), (
        f"{SIGNOFF_DOCUMENT}: expected unique IDs {SIGNOFF_IDS!r}; found {tuple(sorted(seen_ids))!r}"
    )

    detail_ids = set(DETAIL_HEADING.findall(signoff_text))
    assert detail_ids == set(SIGNOFF_IDS), (
        f"{SIGNOFF_DOCUMENT}: detail headings must cover {SIGNOFF_IDS!r}; "
        f"found {tuple(sorted(detail_ids))!r}"
    )
    lower_anchor_ids = set(DETAIL_ANCHOR.findall(signoff_text))
    expected_lower_anchors = {signoff_id.lower() for signoff_id in SIGNOFF_IDS}
    assert lower_anchor_ids == expected_lower_anchors, (
        f"{SIGNOFF_DOCUMENT}: detail anchors must cover {sorted(expected_lower_anchors)!r}; "
        f"found {sorted(lower_anchor_ids)!r}"
    )

    plan_links = _plan_signoff_links(_read_document(PLAN_DOCUMENT))
    assert {signoff_id for signoff_id, _ in plan_links} == seen_ids, (
        f"{PLAN_DOCUMENT} and {SIGNOFF_DOCUMENT}: plan links and checklist IDs differ; "
        f"plan={sorted({signoff_id for signoff_id, _ in plan_links})!r}, "
        f"checklist={sorted(seen_ids)!r}"
    )
