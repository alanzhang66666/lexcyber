from pathlib import Path

from storage.postgres.repository import connection

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def split_sql(script: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    for line in script.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        current.append(line)
        if stripped.endswith(";"):
            statement = "\n".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
    if current:
        statements.append("\n".join(current).strip())
    return statements


def apply_migrations() -> None:
    with connection() as conn:
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            for statement in split_sql(path.read_text(encoding="utf-8")):
                conn.execute(statement)
