from __future__ import annotations

import json
from pathlib import Path

from skill_runtime.errors import SkillDisabledError, SkillNotFoundError
from skill_runtime.schemas import SkillManifest

CATALOG_PATH = Path(__file__).resolve().parents[1] / "skills" / "catalog.json"
CORE_CATALOG_PATH = Path(__file__).resolve().parents[1] / "skills" / "core_catalog.json"


def load_catalog(path: Path | None = None) -> list[SkillManifest]:
    catalog_path = path or CATALOG_PATH
    raw = json.loads(catalog_path.read_text(encoding="utf-8"))
    return [SkillManifest.model_validate(item) for item in raw]


class SkillRegistry:
    """Loads registered skills from catalog.json, with optional status overlays."""

    def __init__(self, catalog_path: Path | None = None, manifests: list[SkillManifest] | None = None, packs: set[str] | None = None):
        loaded = manifests if manifests is not None else load_catalog(catalog_path)
        if packs is not None:
            if "core" in packs:
                loaded.extend(load_catalog(CORE_CATALOG_PATH))
            loaded = [item for item in loaded if item.pack in packs]
        self._manifests = {self._key(item): item for item in loaded}
        self._overrides: dict[tuple[str, str], dict[str, object]] = {}

    @staticmethod
    def _key(manifest: SkillManifest) -> tuple[str, str]:
        return (manifest.id, manifest.version)

    def all(self) -> list[SkillManifest]:
        items: list[SkillManifest] = []
        for key, manifest in self._manifests.items():
            overlay = self._overrides.get(key, {})
            items.append(manifest.model_copy(update=overlay))
        return items

    def list(self, include_disabled: bool = False) -> list[SkillManifest]:
        items = self.all()
        if include_disabled:
            return items
        return [item for item in items if item.enabled and item.status == "active"]

    def versions(self, skill_id: str) -> list[SkillManifest]:
        return [item for item in self.all() if item.id == skill_id]

    def set_status(self, skill_id: str, version: str, *, enabled: bool | None = None, status: str | None = None) -> None:
        key = (skill_id, version)
        if key not in self._manifests:
            raise SkillNotFoundError(f"skill is not registered: {skill_id}@{version}")
        overlay = dict(self._overrides.get(key, {}))
        if enabled is not None:
            overlay["enabled"] = enabled
            overlay["status"] = "active" if enabled else "disabled"
        if status is not None:
            overlay["status"] = status
            overlay["enabled"] = status == "active"
        self._overrides[key] = overlay

    def get(self, skill_id: str, version: str | None = None, *, allow_disabled: bool = False) -> SkillManifest:
        matches = [item for item in self.all() if item.id == skill_id]
        if version:
            matches = [item for item in matches if item.version == version]
        else:
            matches = sorted(matches, key=lambda item: item.version, reverse=True)
        if not matches:
            raise SkillNotFoundError(f"skill is not registered: {skill_id}@{version or 'latest'}")
        manifest = matches[0]
        if not allow_disabled and (not manifest.enabled or manifest.status == "disabled"):
            raise SkillDisabledError(f"skill is disabled: {manifest.id}@{manifest.version}")
        return manifest
