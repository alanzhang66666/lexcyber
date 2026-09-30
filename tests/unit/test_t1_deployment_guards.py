from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _env_value(name: str) -> str:
    for line in (ROOT / "deploy/ecs-upload/.env.v03.example").read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1]
    raise AssertionError(f"missing {name} in ECS environment example")


def test_ecs_example_does_not_ship_deployable_placeholder_secrets() -> None:
    for name in (
        "POSTGRES_PASSWORD",
        "APP_DB_PASSWORD",
        "ENGINE_DB_PASSWORD",
        "ENGINE_SERVICE_TOKEN",
        "MINIO_ROOT_PASSWORD",
    ):
        assert _env_value(name) == ""


def test_ecs_startup_rejects_placeholder_secrets_before_docker() -> None:
    script = (ROOT / "deploy/ecs-upload/start-on-ecs.sh").read_text(encoding="utf-8")
    assert "must be a generated secret" in script
    assert "change-me*" in script
    assert "POSTGRES_PASSWORD APP_DB_PASSWORD ENGINE_DB_PASSWORD ENGINE_SERVICE_TOKEN" in script


def test_java_receives_model_configuration_security_environment() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    java_block = compose.split("  java:\n", 1)[1].split("  engine:\n", 1)[0]
    for name in (
        "MODEL_PROVIDER",
        "MODEL_NAME",
        "MODEL_API_KEY",
        "MODEL_API_BASE_URL",
        "MODEL_API_BASE_URL_ALLOWLIST",
        "MODEL_CONFIG_ADMIN_USERNAMES",
        "MODEL_TIMEOUT_SECONDS",
    ):
        assert f"{name}:" in java_block


def test_java_default_flyway_path_is_the_app_migration_line() -> None:
    application = (ROOT / "server/src/main/resources/application.yml").read_text(encoding="utf-8")
    assert "locations: ${SPRING_FLYWAY_LOCATIONS:classpath:db/migration/app}" in application
    assert "schemas: ${SPRING_FLYWAY_SCHEMAS:app}" in application
    assert "default-schema: ${SPRING_FLYWAY_DEFAULT_SCHEMA:app}" in application
