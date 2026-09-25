"""Declarative quality-gate checks for the iterative delivery plan.

This module intentionally contains data only.  It does not inspect the
filesystem, start subprocesses, or perform any other work at import time.
"""

from __future__ import annotations

from dataclasses import dataclass

ROOT_GATE = "root"
SUBMISSION_GATE = "submission"
SCAN_GATE = "scan"
RELEASE_GATE = "release"
GATES = (ROOT_GATE, SUBMISSION_GATE, SCAN_GATE, RELEASE_GATE)

PASSED = "通过"
FAILED = "失败"
SKIPPED = "跳过"

SUBMISSION_ROOT = "competition_submission/1-智能体作品及其完整材料"


@dataclass(frozen=True)
class Check:
    """One declarative quality-gate check.

    ``command`` is an argv tuple and is intentionally not a shell command.
    An empty command reserves the check for an in-process runner.
    """

    name: str
    gate: str
    command: tuple[str, ...]
    cwd: str
    tools: tuple[str, ...]
    release_only: bool = False
    ci_job: str | None = None
    ci_marker: str | None = None
    requirement: str = ""
    note: str = ""


@dataclass(frozen=True)
class CheckOutcome:
    """Result shape shared by the quality-gate executor and its summary."""

    check: Check
    state: str
    reason: str = ""
    missing_tools: tuple[str, ...] = ()
    detail: str = ""
    winerror5: bool = False


@dataclass(frozen=True)
class ScanRule:
    """One deny rule used by the staged-content scanning gate.

    The allowlist below is intentionally descriptive only.  It is not
    consulted as an exemption by the future scanner: deny rules always win.
    ``pattern`` is a regular expression for every kind except ``size``, where
    it is the decimal byte threshold and a file is denied when its size is
    strictly greater than that threshold.
    """

    name: str
    kind: str
    pattern: str
    requirement: str


MAX_SCAN_FILE_BYTES = 100 * 1024 * 1024

# The rule table is data-only.  Path rules are written for normalized Git
# paths (forward slashes); the runner is responsible for choosing the target
# value for each rule kind.
SCAN_RULES = (
    ScanRule(
        name="真实环境文件",
        kind="filename",
        pattern=r"^(?:\.env|\.env\.(?!(?:example|v03\.example)$)[A-Za-z0-9_.-]+)$",
        requirement="4.2",
    ),
    ScanRule(
        name="演示账号环境文件",
        kind="filename",
        pattern=r"^demo-account\.env$",
        requirement="4.2",
    ),
    ScanRule(
        name="私钥内容",
        kind="content",
        pattern=r"-----BEGIN (RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----",
        requirement="4.3",
    ),
    ScanRule(
        name="通用访问令牌",
        kind="content",
        pattern=r"\b(sk|rk|ghp|gho|ghs|glpat)[-_][A-Za-z0-9]{16,}\b",
        requirement="4.3",
    ),
    ScanRule(
        name="AWS 访问密钥标识",
        kind="content",
        pattern=r"\b(AKIA|ASIA)[0-9A-Z]{16}\b",
        requirement="4.3",
    ),
    ScanRule(
        name="内联密钥赋值",
        kind="content",
        pattern=r'''(?i)\b(api[_-]?key|secret|password|token)\s*[:=]\s*["']?[^\s"'#]{12,}''',
        requirement="4.3",
    ),
    ScanRule(
        name="部署上传打包",
        kind="path",
        pattern=r"^deploy/ecs-upload\.tar$",
        requirement="4.5, 4.6",
    ),
    ScanRule(
        name="镜像 tar",
        kind="path",
        pattern=r"\.tar(\.gz)?$",
        requirement="4.5, 4.6",
    ),
    ScanRule(
        name="部署运行数据",
        kind="path",
        pattern=(
            r"^deploy/ecs-upload/"
            r"(?!README\.md$)(?!\.env\.v03\.example$)(?!start-on-ecs\.sh$)"
        ),
        requirement="4.5, 4.7",
    ),
    ScanRule(
        name="原始法学材料",
        kind="path",
        pattern=r"(?:^|/)(?:法学材料|\.tmp-legal-docs)(?:/|$)",
        requirement="4.5, 4.6",
    ),
    ScanRule(
        name="依赖与构建产物",
        kind="path",
        pattern=(
            r"(?:^|/)(?:node_modules|target|dist|__pycache__|\.pytest_cache|"
            r"\.ruff_cache|build|\.vite|coverage)(?:/|$)"
        ),
        requirement="4.5, 4.6",
    ),
    ScanRule(
        name="临时与断点文件",
        kind="path",
        pattern=r"(?:^\.t1-.*|^\.tmp-.*|\.checkpoint\.json(?:\.lock)?$)",
        requirement="4.5, 4.6",
    ),
    ScanRule(
        name="单文件体积上限",
        kind="size",
        pattern=str(MAX_SCAN_FILE_BYTES),
        requirement="4.4",
    ),
)

# This is a self-check inventory, not a bypass list.  The first two groups
# describe prefixes/files that should remain clean under SCAN_RULES.  The
# final expression deliberately excludes root-level .t1-* and .tmp-* files,
# because those names must still be denied by the temporary-file rule.
SCAN_ALLOWED_PREFIXES = (
    "engine/",
    "models/",
    "graph/",
    "skill_runtime/",
    "skills/",
    "retrieval/",
    "agents/",
    "audit/",
    "config/",
    "prompts/",
    "storage/",
    "tools/",
    "server/src/",
    "web/src/",
    "contracts/",
    "scripts/",
    "tests/",
    "docs/",
    "nginx/",
    "competition_submission/1-智能体作品及其完整材料/",
)
SCAN_ALLOWED_FILES = (
    "deploy/ecs-upload/README.md",
    "deploy/ecs-upload/.env.v03.example",
    "deploy/ecs-upload/start-on-ecs.sh",
    ".env.example",
    ".env.v03.example",
    ".gitignore",
    ".dockerignore",
)
SCAN_ALLOWED_ROOT_MARKDOWN_PATTERN = r"^(?!\.t1-)(?!\.tmp-)[^/]+\.md$"
SCAN_ALLOWLIST = SCAN_ALLOWED_PREFIXES + SCAN_ALLOWED_FILES + (
    SCAN_ALLOWED_ROOT_MARKDOWN_PATTERN,
)


# Contract/frontend field, environment variable, and Settings attribute.
MODEL_CONFIG_FIELDS = (
    ("provider", "MODEL_PROVIDER", "model_provider"),
    ("modelName", "MODEL_NAME", "model_name"),
    ("apiBaseUrl", "MODEL_API_BASE_URL", "model_api_base_url"),
    ("apiKey", "MODEL_API_KEY", "model_api_key"),
    ("timeoutSeconds", "MODEL_TIMEOUT_SECONDS", "model_timeout_seconds"),
)

PROBE_RECORD_FIELDS = (
    "taskId",
    "resultId",
    "provider",
    "model",
    "latencyMs",
    "schemaVersion",
)


# Root system gate: the twelve checks mirrored by the root CI jobs.
_ROOT_CHECKS = (
    Check(
        name="ruff 静态检查",
        gate=ROOT_GATE,
        command=("python", "-m", "ruff", "check", "."),
        cwd=".",
        tools=("python",),
        ci_job="test",
        ci_marker="ruff check .",
        requirement="3.2, 3.5",
    ),
    Check(
        name="0.2 边界守卫",
        gate=ROOT_GATE,
        command=(),
        cwd=".",
        tools=(),
        ci_job="test",
        ci_marker=r"^\s*(from|import)\s+(apps|domain)\b",
        requirement="3.2",
        note="遍历 engine、models、graph、skill_runtime、skills、retrieval 的 Python 文件。",
    ),
    Check(
        name="pytest 非集成",
        gate=ROOT_GATE,
        command=("python", "-m", "pytest", "-q", "-m", "not integration"),
        cwd=".",
        tools=("python",),
        ci_job="test",
        ci_marker='pytest -q -m "not integration"',
        requirement="3.2",
    ),
    Check(
        name="Compose 配置校验",
        gate=ROOT_GATE,
        command=("docker", "compose", "-f", "docker-compose.yml", "config", "--quiet"),
        cwd=".",
        tools=("docker",),
        ci_job="test",
        ci_marker="docker compose -f docker-compose.yml config --quiet",
        requirement="3.2",
    ),
    Check(
        name="Java 单元测试",
        gate=ROOT_GATE,
        command=("mvn", "-B", "test"),
        cwd="server",
        tools=("mvn",),
        ci_job="java",
        ci_marker="mvn -B test",
        requirement="3.2",
    ),
    Check(
        name="web 依赖安装",
        gate=ROOT_GATE,
        command=("npm", "ci"),
        cwd="web",
        tools=("npm",),
        ci_job="web",
        ci_marker="npm ci",
        requirement="3.2",
    ),
    Check(
        name="web 类型检查",
        gate=ROOT_GATE,
        command=("npm", "run", "typecheck"),
        cwd="web",
        tools=("npm",),
        ci_job="web",
        ci_marker="npm run typecheck",
        requirement="3.2",
    ),
    Check(
        name="web 单元测试",
        gate=ROOT_GATE,
        command=("npm", "test"),
        cwd="web",
        tools=("npm",),
        ci_job="web",
        ci_marker="npm test",
        requirement="3.2",
    ),
    Check(
        name="web 构建",
        gate=ROOT_GATE,
        command=("npm", "run", "build"),
        cwd="web",
        tools=("npm",),
        ci_job="web",
        ci_marker="npm run build",
        requirement="3.2",
    ),
    Check(
        name="公开契约校验",
        gate=ROOT_GATE,
        command=("openapi-spec-validator", "contracts/public-api.yaml"),
        cwd=".",
        tools=("openapi-spec-validator",),
        ci_job="contracts",
        ci_marker="openapi-spec-validator contracts/public-api.yaml",
        requirement="3.2",
    ),
    Check(
        name="内部契约校验",
        gate=ROOT_GATE,
        command=("openapi-spec-validator", "contracts/internal-engine-api.yaml"),
        cwd=".",
        tools=("openapi-spec-validator",),
        ci_job="contracts",
        ci_marker="openapi-spec-validator contracts/internal-engine-api.yaml",
        requirement="3.2",
    ),
    Check(
        name="类型快照守卫",
        gate=ROOT_GATE,
        command=("python", "scripts/check_openapi_snapshot.py"),
        cwd=".",
        tools=("python",),
        ci_job="contracts",
        ci_marker="python scripts/check_openapi_snapshot.py",
        requirement="3.2",
    ),
)


# Root-system focused checks that are not individual CI commands.
_SPECIALIZED_ROOT_CHECKS = (
    Check(
        name="三案数据校验",
        gate=ROOT_GATE,
        command=(
            "python",
            "-m",
            "pytest",
            "-q",
            "tests/unit/test_t3_three_case_demo.py",
            "tests/unit/test_t3_engine_runners.py",
        ),
        cwd=".",
        tools=("python",),
        requirement="3.3",
    ),
    Check(
        name="三案数据集报告",
        gate=ROOT_GATE,
        command=("python", "scripts/validate_three_case_demo.py"),
        cwd=".",
        tools=("python",),
        requirement="3.3",
    ),
    Check(
        name="导入包安全限制校验",
        gate=ROOT_GATE,
        command=("python", "-m", "pytest", "-q", "tests/unit/test_import_package.py"),
        cwd=".",
        tools=("python",),
        requirement="3.3",
    ),
    Check(
        name="租约 fencing 校验",
        gate=ROOT_GATE,
        command=("mvn", "-B", "test", "-Dtest=ImportStoreLeaseTest"),
        cwd="server",
        tools=("mvn", "docker"),
        requirement="3.3",
        note="Testcontainers 使用 postgres:16.4-alpine；可用 TEST_JDBC_URL 改用外部数据库。",
    ),
    Check(
        name="事件材料回填校验",
        gate=ROOT_GATE,
        command=(
            "python",
            "-m",
            "pytest",
            "-q",
            "tests/unit/test_t3_three_case_demo.py::test_t1_case_create_maps_case_b_comparison_events_to_their_own_documents",
            "tests/unit/test_t3_three_case_demo.py::test_t1_case_create_uses_uploaded_document_ids_and_string_locators",
        ),
        cwd=".",
        tools=("python",),
        requirement="3.3",
    ),
    Check(
        name="量刑重放校验",
        gate=ROOT_GATE,
        command=(
            "python",
            "-m",
            "pytest",
            "-q",
            "tests/unit/test_t3_three_case_demo.py::test_section_six_reviewed_dispositions_are_registered_and_replayed",
            "tests/unit/test_t3_three_case_demo.py::test_case_b_009_reviewed_range_is_replayed_without_synthetic_arithmetic",
            "tests/unit/test_t3_three_case_demo.py::test_approved_sentencing_rule_replays_transparent_arithmetic",
        ),
        cwd=".",
        tools=("python",),
        requirement="3.3",
    ),
    Check(
        name="模型链路保留校验",
        gate=ROOT_GATE,
        command=(
            "python",
            "-m",
            "pytest",
            "-q",
            "tests/unit/test_model_probe.py",
            "tests/unit/test_model_gateway.py",
        ),
        cwd=".",
        tools=("python",),
        requirement="9.10",
        note="覆盖 ModelProbeRunner 与 ModelGateway 的模型调用链路保留行为。",
    ),
    Check(
        name="模型路由映射保留校验",
        gate=ROOT_GATE,
        command=("python", "-m", "pytest", "-q", "tests/unit/test_model_chain_retention.py"),
        cwd=".",
        tools=("python",),
        requirement="9.1, 9.5, 9.7, 9.12",
        note=(
            "覆盖五字段四处同名可读与 EngineDispatcher 的 model.probe -> model_probe 映射；"
            "五字段由 MODEL_CONFIG_FIELDS 定义。"
        ),
    ),
)


# Submission-directory gate.  Every working directory deliberately starts
# with SUBMISSION_ROOT so the executor can resolve all paths from the
# repository root without special cases.
_SUBMISSION_CHECKS = (
    Check(
        name="交付完整性验收",
        gate=SUBMISSION_GATE,
        command=("python", "tests/acceptance/verify_delivery.py"),
        cwd=SUBMISSION_ROOT,
        tools=("python",),
        requirement="3.4",
    ),
    Check(
        name="比赛 Python 单测",
        gate=SUBMISSION_GATE,
        command=("python", "-m", "pytest", "-q", "-m", "not integration and not e2e"),
        cwd=SUBMISSION_ROOT,
        tools=("python",),
        requirement="3.4",
        note='pytest.ini 仅声明 integration 标记；e2e 未声明，但未启用 strict-markers。',
    ),
    Check(
        name="比赛 Java 测试",
        gate=SUBMISSION_GATE,
        command=("mvn", "-B", "test"),
        cwd=f"{SUBMISSION_ROOT}/src/server",
        tools=("mvn",),
        requirement="3.4",
    ),
    Check(
        name="比赛 web 依赖安装",
        gate=SUBMISSION_GATE,
        command=("npm", "ci"),
        cwd=f"{SUBMISSION_ROOT}/src/web",
        tools=("npm",),
        requirement="3.4",
    ),
    Check(
        name="比赛 web 类型检查",
        gate=SUBMISSION_GATE,
        command=("npm", "run", "typecheck"),
        cwd=f"{SUBMISSION_ROOT}/src/web",
        tools=("npm",),
        requirement="3.4",
    ),
    Check(
        name="比赛 web 单测",
        gate=SUBMISSION_GATE,
        command=("npm", "test"),
        cwd=f"{SUBMISSION_ROOT}/src/web",
        tools=("npm",),
        requirement="3.4",
    ),
    Check(
        name="比赛 web 构建",
        gate=SUBMISSION_GATE,
        command=("npm", "run", "build"),
        cwd=f"{SUBMISSION_ROOT}/src/web",
        tools=("npm",),
        requirement="3.4",
    ),
    Check(
        name="比赛公开契约校验",
        gate=SUBMISSION_GATE,
        command=("openapi-spec-validator", "src/contracts/public-api.yaml"),
        cwd=SUBMISSION_ROOT,
        tools=("openapi-spec-validator",),
        requirement="3.4",
    ),
    Check(
        name="比赛内部契约校验",
        gate=SUBMISSION_GATE,
        command=("openapi-spec-validator", "src/contracts/internal-engine-api.yaml"),
        cwd=SUBMISSION_ROOT,
        tools=("openapi-spec-validator",),
        requirement="3.4",
    ),
    Check(
        name="比赛语法扫描",
        gate=SUBMISSION_GATE,
        command=(),
        cwd=SUBMISSION_ROOT,
        tools=("python",),
        requirement="3.4",
        note=(
            "执行比赛目录 JSON、YAML 与 Python 语法校验；pytest.ini 未声明 e2e 标记，"
            "但未启用 strict-markers。"
        ),
    ),
)


# The scan gate examines only staged paths.  Its command is empty because
# task 2.2 will register the in-process runner; keeping the definition here
# makes the gate visible to selection and summary code now.
_SCAN_CHECKS = (
    Check(
        name="提交内容敏感信息与大文件扫描",
        gate=SCAN_GATE,
        command=(),
        cwd=".",
        tools=("git",),
        requirement="4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.9",
        note="仅扫描已暂存文件；deny 规则优先于允许清单。",
    ),
)


# Release-only checks are reserved for the in-process runner implemented by
# the quality-gate executor.  Keeping command empty makes their deferred
# nature explicit without inventing a shell command here.
_RELEASE_CHECKS = (
    Check(
        name="本地 Compose 端到端",
        gate=RELEASE_GATE,
        command=(),
        cwd=".",
        tools=("docker", "python"),
        release_only=True,
        ci_job="compose-e2e",
        ci_marker="docker compose -f docker-compose.yml up -d --build",
        requirement="5.4, 5.5, 5.6",
        note="需要 Docker 与 Compose；Windows 还需 pwsh 执行 ready-check.ps1。",
    ),
    Check(
        name="真实 model.probe",
        gate=RELEASE_GATE,
        command=(),
        cwd=".",
        tools=("python",),
        release_only=True,
        requirement="5.7, 5.8, 5.9, 5.10, 5.11, 5.12",
        note="需要 .env.v03 中的真实模型凭据；只经 Java /v1 公开接口。",
    ),
)


# CI workflow mapping is intentionally declarative.  The workflow itself is
# not modified by this feature; tests can use these markers to detect drift.
CI_WORKFLOW = ".github/workflows/ci.yml"
CI_JOBS = ("test", "java", "web", "contracts", "compose-e2e")
CI_JOB_MAPPING: dict[str, tuple[str, ...]] = {
    "test": (
        "ruff check .",
        r"^\s*(from|import)\s+(apps|domain)\b",
        'pytest -q -m "not integration"',
        "docker compose -f docker-compose.yml config --quiet",
    ),
    "java": ("mvn -B test",),
    "web": ("npm ci", "npm run typecheck", "npm test", "npm run build"),
    "contracts": (
        "openapi-spec-validator contracts/public-api.yaml",
        "openapi-spec-validator contracts/internal-engine-api.yaml",
        "python scripts/check_openapi_snapshot.py",
    ),
    "compose-e2e": (
        "docker compose -f docker-compose.yml up -d --build",
        "/healthz",
        "waiting_review",
    ),
}


# Keep one ordered collection as the executor and tests' source of truth.
CHECKS = _ROOT_CHECKS + _SPECIALIZED_ROOT_CHECKS + _SUBMISSION_CHECKS + _SCAN_CHECKS + _RELEASE_CHECKS


__all__ = [
    "Check",
    "CheckOutcome",
    "ScanRule",
    "CHECKS",
    "CI_JOB_MAPPING",
    "CI_JOBS",
    "CI_WORKFLOW",
    "FAILED",
    "GATES",
    "MAX_SCAN_FILE_BYTES",
    "MODEL_CONFIG_FIELDS",
    "PASSED",
    "PROBE_RECORD_FIELDS",
    "RELEASE_GATE",
    "ROOT_GATE",
    "SCAN_ALLOWED_FILES",
    "SCAN_ALLOWED_PREFIXES",
    "SCAN_ALLOWED_ROOT_MARKDOWN_PATTERN",
    "SCAN_ALLOWLIST",
    "SCAN_GATE",
    "SCAN_RULES",
    "SKIPPED",
    "SUBMISSION_GATE",
    "SUBMISSION_ROOT",
]
