"""Optional local entrypoint; production Compose uses the Dramatiq CLI."""

from storage.postgres.repository import init_db
from storage.redis import configure_broker


def main() -> None:
    init_db()
    configure_broker()


if __name__ == "__main__":
    main()
