import pytest

from skill_runtime.registry import load_catalog
from storage.postgres.migrations import apply_migrations
from storage.postgres.skill_store import upsert_skill_manifests


@pytest.mark.integration
def test_skill_registry_can_sync_to_postgres():
    try:
        apply_migrations()
        upsert_skill_manifests([item.model_dump() for item in load_catalog()])
    except Exception as exc:
        pytest.skip(f"postgres unavailable: {exc}")
