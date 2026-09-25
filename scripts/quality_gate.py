"""Execute the declarative quality gates.

The check definitions live in :mod:`scripts.quality_gate_checks`; this module
only provides selection, process execution, masking, and presentation.  It is
safe to import: no files are read and no subprocess is started at import time.

The in-process runner registry contains the 0.2 import-boundary guard,
competition-directory syntax validation, and staged-content scanning.  Compose
and model-probe runners remain unregistered until their respective increments.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable, Sequence

try:
    from scripts.quality_gate_checks import (
        CHECKS,
        FAILED,
        GATES,
        MAX_SCAN_FILE_BYTES,
        PASSED,
        RELEASE_GATE,
        SCAN_RULES,
        Check,
        CheckOutcome,
        ScanRule,
        SKIPPED,
    )
except ModuleNotFoundError:  # direct ``python scripts/quality_gate.py`` execution
    from quality_gate_checks import (  # type: ignore[no-redef]
        CHECKS,
        FAILED,
        GATES,
        MAX_SCAN_FILE_BYTES,
        PASSED,
        RELEASE_GATE,
        SCAN_RULES,
        Check,
        CheckOutcome,
        ScanRule,
        SKIPPED,
    )

MASK = "***MASKED***"
MASK_MIN_LEN = 8
WINERROR5_PATTERN = re.compile(r"WinError\s*5\b|\[Errno\s*13\].*WinError\s*5", re.IGNORECASE)
WSL_HINT = "该结果受 Windows 平台限制影响，须在 Linux 或 WSL 的 Python 3.12 环境复跑后再判定。"

DEFAULT_GATES = ("root", "submission", "scan")
SUMMARY_TAIL_LINES = 40


@dataclass(frozen=True)
class Context:
    """Runtime context passed to an in-process check runner."""

    repo_root: Path
    check: Check
    secrets: tuple[str, ...] = ()


@dataclass(frozen=True)
class StagedEntry:
    """A staged path and the safe-to-scan content available in the worktree."""

    path: str
    size: int
    text: str | None


@dataclass(frozen=True)
class ScanHit:
    """One deny-rule match produced by the pure staged-content scanner."""

    path: str
    rule: str
    value: str | None = None

    @property
    def rule_name(self) -> str:
        """Compatibility alias for callers that use the explicit field name."""

        return self.rule


@dataclass(frozen=True)
class Selection:
    """A check selected for execution, or a check already marked as skipped.

    Selected entries have ``selected=True`` and no outcome yet.  Skipped
    entries carry their final ``CheckOutcome``.  Convenience properties make
    the selection easy to inspect without exposing mutable execution state.
    """

    check: Check
    selected: bool
    outcome: CheckOutcome | None = None

    @property
    def state(self) -> str | None:
        return self.outcome.state if self.outcome is not None else None

    @property
    def reason(self) -> str:
        return self.outcome.reason if self.outcome is not None else ""

    @property
    def missing_tools(self) -> tuple[str, ...]:
        return self.outcome.missing_tools if self.outcome is not None else ()


@dataclass(frozen=True)
class SubprocessResult:
    """Small, testable representation of a non-shell subprocess invocation."""

    argv: tuple[str, ...]
    returncode: int
    stdout: str = ""
    stderr: str = ""
    winerror5: bool = False

    @property
    def args(self) -> tuple[str, ...]:
        """Expose the conventional ``CompletedProcess.args`` spelling too."""

        return self.argv


def mask(text: str, secrets_: Iterable[str]) -> str:
    """Replace sufficiently long secret values with the single mask token.

    Values shorter than ``MASK_MIN_LEN`` are deliberately ignored so ordinary
    short configuration values are not transformed into an ambiguous stream
    of masks.  Longer values are replaced longest-first, preventing a shorter
    secret from partially exposing a longer one.
    """

    masked = text
    values = {
        value
        for value in secrets_
        if isinstance(value, str) and value and len(value) >= MASK_MIN_LEN
    }
    for value in sorted(values, key=len, reverse=True):
        masked = masked.replace(value, MASK)
    return masked


def mask_hit_value(value: str) -> str:
    """Render a suspicious value without exposing the value itself.

    The first three characters are retained for recognition, followed by an
    ellipsis and the original length.  The full value is never returned.
    """

    if not value:
        return "…（长度 0）"
    return f"{value[:3]}…（长度 {len(value)}）"


def staged_paths(repo_root: Path) -> list[str]:
    """Return paths reported by the staged index, using one Git operation."""

    completed = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "-z"],
        cwd=str(repo_root),
        check=True,
        capture_output=True,
        text=False,
        shell=False,
    )
    output = completed.stdout or b""
    if isinstance(output, bytes):
        output = output.decode("utf-8", errors="surrogateescape")
    return [path for path in output.split("\0") if path]


def staged_size(repo_root: Path, path: str) -> int:
    """Read a staged path's size, preferring the worktree before Git."""

    worktree_path = repo_root / Path(path)
    try:
        return worktree_path.stat().st_size
    except (OSError, ValueError):
        completed = subprocess.run(
            ["git", "cat-file", "-s", f":{path}"],
            cwd=str(repo_root),
            check=True,
            capture_output=True,
            text=True,
            shell=False,
        )
        output = completed.stdout or ""
        if isinstance(output, bytes):
            output = output.decode("ascii", errors="strict")
        return int(output.strip())


def scan(entries: Sequence[StagedEntry], rules: Sequence[ScanRule]) -> list[ScanHit]:
    """Apply scan rules to entries without reading files or starting processes."""

    hits: list[ScanHit] = []
    for entry in entries:
        normalized_path = entry.path.replace("\\", "/")
        filename = PurePosixPath(normalized_path).name
        for rule in rules:
            matched = None
            if rule.kind == "filename":
                matched = re.search(rule.pattern, filename)
            elif rule.kind == "path":
                matched = re.search(rule.pattern, normalized_path)
            elif rule.kind == "content":
                if entry.text is not None:
                    matched = re.search(rule.pattern, entry.text)
            elif rule.kind == "size":
                if entry.size > int(rule.pattern):
                    matched = True
            else:
                raise ValueError(f"未知扫描规则类型: {rule.kind}")

            if not matched:
                continue

            if rule.kind == "content":
                value = mask_hit_value(matched.group(0))
            elif rule.kind == "size":
                value = f"{entry.size} bytes"
            else:
                value = None
            hits.append(ScanHit(path=entry.path, rule=rule.name, value=value))
    return hits


def _is_winerror5(value: object) -> bool:
    """Return whether an exception or output contains the Windows error."""

    if isinstance(value, BaseException) and getattr(value, "winerror", None) == 5:
        return True
    return bool(WINERROR5_PATTERN.search(str(value)))


def _combined_output(stdout: str = "", stderr: str = "") -> str:
    """Combine process streams for one bounded diagnostic summary."""

    parts = [part for part in (stdout, stderr) if part]
    return "\n".join(parts)


def output_tail(text: str, secrets_: Iterable[str] = (), *, lines: int = SUMMARY_TAIL_LINES) -> str:
    """Mask text and retain only its final ``lines`` lines."""

    masked = mask(text, secrets_)
    if not masked:
        return ""
    return "\n".join(masked.splitlines()[-lines:])


def require_tools(tools: Iterable[str]) -> tuple[str, ...]:
    """Return executable names that are not available on ``PATH``."""

    missing: list[str] = []
    seen: set[str] = set()
    for tool in tools:
        if not tool or tool in seen:
            continue
        seen.add(tool)
        if shutil.which(tool) is None:
            missing.append(tool)
    return tuple(missing)


def run_subprocess(argv: Sequence[str], cwd: str | Path) -> SubprocessResult:
    """Run ``argv`` without a shell and capture both output streams.

    A missing working directory and process-launch errors are represented as a
    failed result rather than raised to the CLI.  This keeps every check in the
    same three-state summary path and makes the function straightforward to
    test by replacing ``subprocess.run``.
    """

    args = tuple(str(argument) for argument in argv)
    working_directory = Path(cwd)
    if not working_directory.is_dir():
        return SubprocessResult(
            argv=args,
            returncode=1,
            stderr=f"cwd 不存在: {working_directory}",
        )

    try:
        completed = subprocess.run(
            list(args),
            cwd=str(working_directory),
            check=False,
            capture_output=True,
            text=True,
            shell=False,
        )
    except PermissionError as exc:
        error_text = f"{type(exc).__name__}: {exc}"
        return SubprocessResult(
            argv=args,
            returncode=1,
            stderr=error_text,
            winerror5=_is_winerror5(exc),
        )
    except OSError as exc:
        error_text = f"{type(exc).__name__}: {exc}"
        return SubprocessResult(
            argv=args,
            returncode=1,
            stderr=error_text,
            winerror5=_is_winerror5(exc),
        )

    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    winerror5 = _is_winerror5(stdout) or _is_winerror5(stderr)
    return SubprocessResult(
        argv=args,
        returncode=completed.returncode,
        stdout=stdout,
        stderr=stderr,
        winerror5=winerror5,
    )


BOUNDARY_DIRECTORIES = (
    "engine",
    "models",
    "graph",
    "skill_runtime",
    "skills",
    "retrieval",
)
BOUNDARY_PATTERN = re.compile(r"^\s*(from|import)\s+(apps|domain)\b")


SYNTAX_EXCLUDED_DIRECTORIES = frozenset(
    {"node_modules", "target", "dist", "__pycache__"}
)


def _run_boundary_guard(context: Context) -> CheckOutcome:
    """Reject engine-side imports from the removed 0.2 packages.

    The expression intentionally matches the one in ``ci.yml``.  Files are
    read directly rather than imported, and sorted traversal keeps failure
    details stable for both humans and tests.
    """

    violations: list[str] = []
    for directory_name in BOUNDARY_DIRECTORIES:
        directory = context.repo_root / directory_name
        paths = sorted(
            (path for path in directory.rglob("*.py") if path.is_file()),
            key=lambda path: path.as_posix(),
        )
        for path in paths:
            for line_number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(),
                start=1,
            ):
                if BOUNDARY_PATTERN.search(line):
                    relative_path = path.relative_to(context.repo_root).as_posix()
                    violations.append(f"{relative_path}:{line_number}")

    if violations:
        return CheckOutcome(
            check=context.check,
            state=FAILED,
            reason="检测到已删除的 apps/domain 导入",
            detail="\n".join(violations),
        )
    return CheckOutcome(check=context.check, state=PASSED)


def _is_syntax_excluded(path: Path, root: Path) -> bool:
    """Return whether a syntax-scan path belongs to an excluded subtree."""

    relative = path.relative_to(root)
    return path.name == "package-lock.json" or any(
        part in SYNTAX_EXCLUDED_DIRECTORIES for part in relative.parts[:-1]
    )


def _syntax_files(root: Path, suffixes: set[str]) -> list[Path]:
    """Collect syntax-scan files without importing or executing anything."""

    return sorted(
        (
            path
            for path in root.rglob("*")
            if path.is_file()
            and path.suffix.lower() in suffixes
            and not _is_syntax_excluded(path, root)
        ),
        key=lambda path: path.relative_to(root).as_posix(),
    )


def _syntax_location(line: int | None, column: int | None) -> str:
    """Render a one-based source location for a syntax diagnostic."""

    return f"{line if line is not None else '?'}:{column if column is not None else '?'}"


def _format_syntax_failure(
    path: Path,
    root: Path,
    message: str,
    *,
    line: int | None = None,
    column: int | None = None,
) -> str:
    """Format a syntax failure using a repository-relative path."""

    relative_path = path.relative_to(root).as_posix()
    return f"{relative_path}:{_syntax_location(line, column)}: {message}"


def _yaml_failure(path: Path, root: Path, error: Exception) -> str:
    """Extract a safe path/line/column diagnostic from a PyYAML error."""

    mark = getattr(error, "problem_mark", None)
    line = getattr(mark, "line", None)
    column = getattr(mark, "column", None)
    if line is not None:
        line += 1
    if column is not None:
        column += 1
    message = getattr(error, "problem", None)
    if not message:
        lines = str(error).splitlines()
        message = lines[0] if lines else type(error).__name__
    return _format_syntax_failure(path, root, message, line=line, column=column)


def _run_submission_syntax(context: Context) -> CheckOutcome:
    """Validate JSON, YAML, and Python syntax in the competition submission.

    The runner only reads source text.  JSON and YAML files are parsed without
    importing project modules, while Python files are passed to ``compile``
    with ``exec`` mode so syntax is checked without execution.
    """

    submission_root = context.repo_root / context.check.cwd
    try:
        import yaml
    except ImportError:
        return CheckOutcome(
            check=context.check,
            state=SKIPPED,
            reason="缺少工具",
            missing_tools=("PyYAML",),
        )

    failures: list[str] = []

    for path in _syntax_files(submission_root, {".json"}):
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            failures.append(
                _format_syntax_failure(
                    path,
                    submission_root,
                    f"JSON: {error.msg}",
                    line=error.lineno,
                    column=error.colno,
                )
            )
        except (OSError, UnicodeError) as error:
            failures.append(
                _format_syntax_failure(
                    path,
                    submission_root,
                    f"JSON: {type(error).__name__}: {error}",
                )
            )

    for source_root_name in ("src", "tests"):
        source_root = submission_root / source_root_name
        if not source_root.is_dir():
            continue
        for path in sorted(
            (candidate for candidate in source_root.rglob("*.py") if candidate.is_file()),
            key=lambda candidate: candidate.relative_to(submission_root).as_posix(),
        ):
            try:
                source = path.read_text(encoding="utf-8")
                compile(source, str(path), "exec")
            except SyntaxError as error:
                failures.append(
                    _format_syntax_failure(
                        path,
                        submission_root,
                        f"Python: {error.msg}",
                        line=error.lineno,
                        column=error.offset,
                    )
                )
            except (OSError, UnicodeError) as error:
                failures.append(
                    _format_syntax_failure(
                        path,
                        submission_root,
                        f"Python: {type(error).__name__}: {error}",
                    )
                )

    for path in _syntax_files(submission_root, {".yaml", ".yml"}):
        try:
            list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
        except yaml.YAMLError as error:
            failures.append(_yaml_failure(path, submission_root, error))
        except (OSError, UnicodeError) as error:
            failures.append(
                _format_syntax_failure(
                    path,
                    submission_root,
                    f"YAML: {type(error).__name__}: {error}",
                )
            )

    if failures:
        return CheckOutcome(
            check=context.check,
            state=FAILED,
            reason="比赛目录存在语法错误",
            detail=mask("\n".join(failures), context.secrets),
        )
    return CheckOutcome(check=context.check, state=PASSED)


def _staged_entry(repo_root: Path, path: str) -> StagedEntry:
    """Build a scan entry while keeping binary and oversized content opaque."""

    size = staged_size(repo_root, path)
    if size > MAX_SCAN_FILE_BYTES:
        return StagedEntry(path=path, size=size, text=None)

    worktree_path = repo_root / Path(path)
    try:
        raw = worktree_path.read_bytes()
    except (OSError, ValueError):
        return StagedEntry(path=path, size=size, text=None)

    if len(raw) > MAX_SCAN_FILE_BYTES or b"\x00" in raw:
        return StagedEntry(path=path, size=size, text=None)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = None
    return StagedEntry(path=path, size=size, text=text)


def _run_staged_scan(context: Context) -> CheckOutcome:
    """Scan only staged paths and return a masked failure summary on hits."""

    entries = [_staged_entry(context.repo_root, path) for path in staged_paths(context.repo_root)]
    hits = scan(entries, SCAN_RULES)
    if not hits:
        return CheckOutcome(check=context.check, state=PASSED)

    details: list[str] = []
    for hit in hits:
        detail = f"{hit.path}\t规则={hit.rule}"
        if hit.value is not None:
            if hit.rule == "单文件体积上限":
                detail += f"\t体积={hit.value}"
            else:
                detail += f"\t值={mask(hit.value, context.secrets)}"
        details.append(detail)
    return CheckOutcome(
        check=context.check,
        state=FAILED,
        reason="暂存内容命中扫描规则",
        detail=mask("\n".join(details), context.secrets),
    )


# Empty-command checks without a registered runner fail safe as a skipped
# check with an explicit missing runner name.  Optional runners from later
# increments deliberately remain absent from this registry.
INTERNAL_RUNNERS: dict[str, Callable[[Context], CheckOutcome]] = {
    "0.2 边界守卫": _run_boundary_guard,
    "比赛语法扫描": _run_submission_syntax,
    "提交内容敏感信息与大文件扫描": _run_staged_scan,
}


def run_internal(check: Check, context: Context) -> CheckOutcome:
    """Run a registered in-process check, or report its missing runner.

    Runner failures are converted to a failed outcome so a malformed file or
    unexpected implementation error cannot crash the quality-gate summary.
    """

    runner = INTERNAL_RUNNERS.get(check.name)
    if runner is None:
        return CheckOutcome(
            check=check,
            state=SKIPPED,
            reason="内建实现未注册",
            missing_tools=(f"internal-runner:{check.name}",),
        )

    try:
        outcome = runner(context)
    except Exception as exc:  # noqa: BLE001 - runner failures are check failures
        detail = mask(f"{type(exc).__name__}: {exc}", context.secrets)
        return CheckOutcome(
            check=check,
            state=FAILED,
            reason="内建检查异常",
            detail=detail,
            winerror5=_is_winerror5(exc),
        )

    if not isinstance(outcome, CheckOutcome):
        detail = f"内建 runner 返回了 {type(outcome).__name__}，预期为 CheckOutcome"
        return CheckOutcome(
            check=check,
            state=FAILED,
            reason="内建检查返回值无效",
            detail=detail,
        )
    return outcome


def select(
    checks: Iterable[Check],
    gates: Iterable[str],
    release: bool,
) -> list[Selection]:
    """Select checks for execution and mark all other checks as skipped.

    ``release_only`` takes precedence over gate membership when ``release`` is
    false, so release checks consistently explain that the caller did not
    declare a release round.  The returned order is exactly the input order.
    """

    selected_gates = set(gates)
    selections: list[Selection] = []
    for check in checks:
        if check.release_only and not release:
            outcome = CheckOutcome(check=check, state=SKIPPED, reason="未声明发布轮")
            selections.append(Selection(check=check, selected=False, outcome=outcome))
        elif check.gate not in selected_gates:
            outcome = CheckOutcome(check=check, state=SKIPPED, reason="未选中")
            selections.append(Selection(check=check, selected=False, outcome=outcome))
        else:
            selections.append(Selection(check=check, selected=True))
    return selections


def _read_env_secrets(path: Path) -> tuple[str, ...]:
    """Read non-empty values from a dotenv-style file for output masking.

    This is intentionally called only while executing checks, never at module
    import time.  Parsing is conservative: comments and malformed lines are
    ignored, and surrounding single or double quotes are removed.
    """

    if not path.is_file():
        return ()

    values: list[str] = []
    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            _, value = line.split("=", 1)
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            if value:
                values.append(value)
    except OSError:
        return ()
    return tuple(values)


def _runtime_secrets(repo_root: Path) -> tuple[str, ...]:
    """Collect only non-empty values from .env.v03 for output masking."""

    return _read_env_secrets(repo_root / ".env.v03")


def _run_external(check: Check, repo_root: Path, secrets_: tuple[str, ...]) -> CheckOutcome:
    result = run_subprocess(check.command, repo_root / check.cwd)
    detail = output_tail(_combined_output(result.stdout, result.stderr), secrets_)
    winerror5 = result.winerror5 or _is_winerror5(detail)

    if result.returncode == 0 and not winerror5:
        return CheckOutcome(check=check, state=PASSED, detail=detail)

    reason = f"命令退出码 {result.returncode}"
    if not result.stderr and not result.stdout and result.returncode != 0:
        reason = "命令未能启动"
    return CheckOutcome(
        check=check,
        state=FAILED,
        reason=reason,
        detail=detail,
        winerror5=winerror5,
    )


def run_check(check: Check, repo_root: Path, secrets_: tuple[str, ...] = ()) -> CheckOutcome:
    """Execute one selected check after tool and command-shape validation."""

    missing = require_tools(check.tools)
    if missing:
        return CheckOutcome(
            check=check,
            state=SKIPPED,
            reason="缺少工具",
            missing_tools=missing,
        )

    if not check.command:
        return run_internal(
            check,
            Context(repo_root=repo_root, check=check, secrets=secrets_),
        )
    return _run_external(check, repo_root, secrets_)


def execute_selection(
    selections: Iterable[Selection],
    repo_root: Path,
    secrets_: tuple[str, ...] = (),
) -> list[CheckOutcome]:
    """Execute selected entries and preserve skipped entries in input order."""

    outcomes: list[CheckOutcome] = []
    for selection in selections:
        if not selection.selected:
            if selection.outcome is None:
                raise ValueError(f"未选中的检查缺少 outcome: {selection.check.name}")
            outcomes.append(selection.outcome)
        else:
            outcomes.append(run_check(selection.check, repo_root, secrets_))
    return outcomes


def exit_code(outcomes: Iterable[CheckOutcome]) -> int:
    """Return 1 for failures, otherwise 2 for missing tools, otherwise 0."""

    results = tuple(outcomes)
    if any(outcome.state == FAILED for outcome in results):
        return 1
    if any(outcome.missing_tools for outcome in results):
        return 2
    return 0


def _command_text(check: Check) -> str:
    if not check.command:
        return "内建检查"
    rendered: list[str] = []
    for argument in check.command:
        if any(character.isspace() for character in argument) or '"' in argument:
            rendered.append('"' + argument.replace('"', '\\\"') + '"')
        else:
            rendered.append(argument)
    return " ".join(rendered)


def format_summary(
    outcomes: Sequence[CheckOutcome],
    secrets_: Iterable[str] = (),
) -> str:
    """Render one primary summary line per check plus bounded details.

    Details are masked again at the final output boundary so a future internal
    runner cannot accidentally bypass the common masking path.
    """

    secret_values = tuple(secrets_)
    lines: list[str] = []
    winerror5_seen = False
    for outcome in outcomes:
        check = outcome.check
        command = _command_text(check)
        reason = mask(outcome.reason, secret_values)
        detail = mask(outcome.detail, secret_values)
        line = f"[{outcome.state}] {check.name} | gate={check.gate} | {command}"
        if reason:
            line += f" | 原因={reason}"
        if outcome.state == SKIPPED and outcome.missing_tools:
            line += f" | 缺少工具={', '.join(outcome.missing_tools)}"
        lines.append(line)

        if detail:
            lines.extend(f"       → {detail_line}" for detail_line in detail.splitlines())
        if outcome.winerror5 or _is_winerror5(reason) or _is_winerror5(detail):
            winerror5_seen = True

    counts = {state: sum(outcome.state == state for outcome in outcomes) for state in (PASSED, FAILED, SKIPPED)}
    code = exit_code(outcomes)
    lines.append(
        f"计数：通过={counts[PASSED]} 失败={counts[FAILED]} 跳过={counts[SKIPPED]}；退出码={code}"
    )
    if winerror5_seen:
        lines.append(WSL_HINT)
    return "\n".join(lines)


def print_check_list(checks: Iterable[Check] = CHECKS) -> None:
    """Print the declarative table without executing any check."""

    for check in checks:
        release = " release_only=True" if check.release_only else ""
        tools = ",".join(check.tools) if check.tools else "-"
        print(
            f"{check.name} | gate={check.gate}{release} | cwd={check.cwd} | "
            f"tools={tools} | command={_command_text(check)}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="执行 LexCyber 迭代交付质量门")
    parser.add_argument(
        "--gate",
        action="append",
        choices=GATES,
        help="选择要执行的门；可重复指定。默认执行 root、submission、scan。",
    )
    parser.add_argument(
        "--release",
        action="store_true",
        help="声明发布轮，并额外选中 release 门。",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="只列出门槛定义，不执行检查。",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point used by ``python scripts/quality_gate.py``."""

    args = build_parser().parse_args(argv)
    if args.list:
        print_check_list()
        return 0

    gates = set(args.gate or DEFAULT_GATES)
    if args.release:
        gates.add(RELEASE_GATE)

    repo_root = Path(__file__).resolve().parents[1]
    secrets_ = _runtime_secrets(repo_root)
    selections = select(CHECKS, gates, args.release)
    outcomes = execute_selection(selections, repo_root, secrets_)
    print(format_summary(outcomes, secrets_))
    return exit_code(outcomes)


__all__ = [
    "Context",
    "DEFAULT_GATES",
    "INTERNAL_RUNNERS",
    "MASK",
    "MASK_MIN_LEN",
    "ScanHit",
    "Selection",
    "StagedEntry",
    "SubprocessResult",
    "SUMMARY_TAIL_LINES",
    "WSL_HINT",
    "WINERROR5_PATTERN",
    "build_parser",
    "execute_selection",
    "exit_code",
    "format_summary",
    "main",
    "mask",
    "mask_hit_value",
    "output_tail",
    "print_check_list",
    "require_tools",
    "run_check",
    "run_internal",
    "run_subprocess",
    "scan",
    "select",
    "staged_paths",
    "staged_size",
]


if __name__ == "__main__":
    raise SystemExit(main())
