"""Deterministic guards for the model-call chain's retained configuration surfaces.

These checks deliberately use only the Python standard library.  They inspect
source text and Python ASTs without importing application modules, starting
services, or depending on external credentials.  The file is a required root
quality-gate criterion, not an optional integration check.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV_EXAMPLE = ROOT / ".env.v03.example"
COMPOSE_FILE = ROOT / "docker-compose.yml"
CONFIG_SETTINGS = ROOT / "config" / "settings.py"
ENGINE_SETTINGS = ROOT / "engine" / "settings.py"
APP_MIGRATION_DIR = ROOT / "server" / "src" / "main" / "resources" / "db" / "migration" / "app"
NEW_MIGRATION = APP_MIGRATION_DIR / "V12__model_access_config.sql"
ENGINE_DISPATCHER = ROOT / "server" / "src" / "main" / "java" / "com" / "lexcyber" / "server" / "engine" / "EngineDispatcher.java"
MODEL_GATEWAY = ROOT / "models" / "gateway.py"
MODEL_ROUTER = ROOT / "models" / "router.py"

MODEL_CONFIG_FIELDS = (
    ("MODEL_PROVIDER", "model_provider"),
    ("MODEL_NAME", "model_name"),
    ("MODEL_API_KEY", "model_api_key"),
    ("MODEL_API_BASE_URL", "model_api_base_url"),
    ("MODEL_TIMEOUT_SECONDS", "model_timeout_seconds"),
)


def _read(path: Path) -> str:
    assert path.is_file(), f"{path}: expected file to exist"
    return path.read_text(encoding="utf-8")


def _service_block(compose_text: str, service: str) -> list[str]:
    """Return one Compose service block without parsing YAML dependencies."""
    lines = compose_text.splitlines()
    header = f"  {service}:"
    start = next((index for index, line in enumerate(lines) if line == header), None)
    assert start is not None, f"{COMPOSE_FILE}: expected service header {header!r}"

    end = len(lines)
    service_header = re.compile(r"^  [A-Za-z0-9][A-Za-z0-9_-]*:.*$")
    for index in range(start + 1, len(lines)):
        if service_header.fullmatch(lines[index]):
            end = index
            break
    return lines[start:end]


def _environment_lines(service_lines: list[str], service: str) -> list[str]:
    header = "    environment:"
    start = next((index for index, line in enumerate(service_lines) if line == header), None)
    assert start is not None, f"{COMPOSE_FILE}: expected {service}.environment block {header!r}"

    end = len(service_lines)
    for index in range(start + 1, len(service_lines)):
        # A service property has exactly four leading spaces; environment
        # entries have six and therefore remain inside this block.
        if re.match(r"^ {4}\S", service_lines[index]):
            end = index
            break
    return service_lines[start + 1 : end]


def _environment_value(environment_lines: list[str], field: str, service: str) -> str:
    pattern = re.compile(rf"^      {re.escape(field)}\s*:\s*(?P<value>.*)$")
    for line in environment_lines:
        match = pattern.match(line)
        if match:
            return match.group("value").strip()
    expected = f"      {field}:"
    raise AssertionError(f"{COMPOSE_FILE}: expected literal {expected!r} in {service}.environment")


def _annotated_fields(path: Path, class_name: str) -> set[str]:
    source = _read(path)
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as error:
        raise AssertionError(f"{path}: expected parseable Python source for {class_name!r}: {error}") from error

    class_node = next(
        (node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name),
        None,
    )
    assert class_node is not None, f"{path}: expected class literal {class_name!r}"
    return {
        node.target.id
        for node in class_node.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }


def test_model_configuration_fields_remain_readable_across_runtime_surfaces() -> None:
    """Feature: iterative-delivery-plan, Property 18: model fields stay named across four surfaces."""
    env_text = _read(ENV_EXAMPLE)
    compose_text = _read(COMPOSE_FILE)
    settings_fields = {
        CONFIG_SETTINGS: _annotated_fields(CONFIG_SETTINGS, "Settings"),
        ENGINE_SETTINGS: _annotated_fields(ENGINE_SETTINGS, "EngineSettings"),
    }

    for environment_name, attribute_name in MODEL_CONFIG_FIELDS:
        env_pattern = re.compile(rf"(?m)^[ \t]*(?:#[ \t]*)?{re.escape(environment_name)}[ \t]*=")
        assert env_pattern.search(env_text), f"{ENV_EXAMPLE}: expected literal {environment_name}="

        for service in ("engine", "engine-worker"):
            environment_lines = _environment_lines(_service_block(compose_text, service), service)
            _environment_value(environment_lines, environment_name, service)

        for path, fields in settings_fields.items():
            assert attribute_name in fields, f"{path}: expected annotated field {attribute_name!r}"


def test_compose_model_workflow_defaults_remain_stub() -> None:
    """Feature: iterative-delivery-plan, Property 18: Compose defaults preserve stub mode."""
    compose_text = _read(COMPOSE_FILE)
    for service in ("engine", "engine-worker"):
        environment_lines = _environment_lines(_service_block(compose_text, service), service)
        for field in ("MODEL_PROVIDER", "WORKFLOW_PROFILE"):
            value = _environment_value(environment_lines, field, service).strip("\"'")
            expected = f"${{{field}:-stub}}"
            assert value == expected, (
                f"{COMPOSE_FILE}: expected {service}.environment {field} default literal {expected!r}; "
                f"found {value!r}"
            )


def test_model_call_parameters_are_config_driven_without_embedded_endpoints_or_keys() -> None:
    """Feature: iterative-delivery-plan, Property 19: model parameters are not hardcoded."""
    gateway_source = _read(MODEL_GATEWAY)
    router_source = _read(MODEL_ROUTER)

    for field in ("model_api_key", "model_api_base_url", "model_timeout_seconds"):
        expected = rf"(?:settings|self\.settings)\.{field}"
        assert re.search(expected, gateway_source), f"{MODEL_GATEWAY}: expected configuration reference {expected!r}"

    route_reference = r"ModelRoute\(\s*config\.model_provider\s*,\s*config\.model_name\s*\)"
    assert re.search(route_reference, router_source), (
        f"{MODEL_ROUTER}: expected literal/config expression {route_reference!r}"
    )

    source_paths = sorted((ROOT / "models").glob("*.py")) + [ROOT / "engine" / "model_probe.py"]
    optional_model_access = ROOT / "engine" / "model_access.py"
    if optional_model_access.is_file():
        source_paths.append(optional_model_access)
    for path in source_paths:
        source = _read(path)
        assert not re.search(r"(?<![A-Za-z0-9_])https?://", source), (
            f"{path}: expected no hard-coded model endpoint URL literal"
        )
        assert not re.search(r"(?<![A-Za-z0-9_])sk-[A-Za-z0-9][A-Za-z0-9_-]*", source), (
            f"{path}: expected no hard-coded API key literal"
        )


def test_app_migration_versions_are_unique_and_new_migration_is_forward_only() -> None:
    """Feature: iterative-delivery-plan, Property 16: app migrations are unique and forward-only."""
    assert APP_MIGRATION_DIR.is_dir(), f"{APP_MIGRATION_DIR}: expected app migration directory"
    migration_pattern = re.compile(r"^V(?P<version>[0-9]+)__[^/]+\.sql$")
    versions: dict[int, Path] = {}

    migrations = sorted(APP_MIGRATION_DIR.glob("*.sql"))
    assert migrations, f"{APP_MIGRATION_DIR}: expected versioned app migration files"
    for migration in migrations:
        match = migration_pattern.fullmatch(migration.name)
        assert match, f"{migration}: expected migration filename literal V<number>__description.sql"
        version = int(match.group("version"))
        assert version not in versions, (
            f"{migration}: expected unique migration version V{version}; "
            f"already declared by {versions[version]}"
        )
        versions[version] = migration

    assert NEW_MIGRATION in migrations, f"{NEW_MIGRATION}: expected newly added forward migration"
    new_match = migration_pattern.fullmatch(NEW_MIGRATION.name)
    assert new_match, f"{NEW_MIGRATION}: expected migration filename literal V<number>__description.sql"
    new_version = int(new_match.group("version"))
    assert new_version > 11, f"{NEW_MIGRATION}: expected migration version greater than 11; found V{new_version}"


def test_engine_dispatcher_retains_model_probe_route_literal_pair() -> None:
    """Feature: iterative-delivery-plan, Property 25: model.probe maps to model_probe."""
    source = _read(ENGINE_DISPATCHER)
    expected_literals = ('"model.probe".equals(taskType)', 'return "model_probe"')
    assert any(all(literal in line for literal in expected_literals) for line in source.splitlines()), (
        f"{ENGINE_DISPATCHER}: expected one line containing both literals "
        f"{expected_literals[0]!r} and {expected_literals[1]!r}"
    )
