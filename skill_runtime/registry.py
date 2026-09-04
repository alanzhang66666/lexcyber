import json
from functools import lru_cache
from pathlib import Path

from skill_runtime.schemas import SkillManifest


class SkillNotFoundError(LookupError):
    pass


CATALOG_PATH = Path(__file__).resolve().parents[1] / "skills" / "catalog.json"


@lru_cache(maxsize=1)
def _load_catalog() -> tuple[SkillManifest, ...]:
    raw = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    return tuple(SkillManifest.model_validate(item) for item in raw)


class SkillRegistry:
    """Loads only skills explicitly registered in the repository catalog."""

    def list(self) -> list[SkillManifest]:
        return [manifest for manifest in _load_catalog() if manifest.enabled]

    def get(self, skill_id: str, version: str | None = None) -> SkillManifest:
        matches = [item for item in self.list() if item.id == skill_id]
        if version:
            matches = [item for item in matches if item.version == version]
        if not matches:
            raise SkillNotFoundError(f"skill is not registered: {skill_id}@{version or 'latest'}")
        return matches[0]
