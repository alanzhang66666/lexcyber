from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REQUIRED = (
    "Dockerfile",
    ".env.example",
    "README.md",
    "SUBMISSION_MANIFEST.md",
    "DEPENDENCIES.md",
    "THIRD_PARTY_NOTICES.md",
    "src/pyproject.toml",
    "src/server/pom.xml",
    "src/web/package.json",
    "src/contracts/public-api.yaml",
    "prompts/system_guardrails_v1.md",
    "prompts/grounded_analysis_v1.md",
    "knowledge/catalog.json",
    "knowledge/sources/legal_sources.json",
    "container/entrypoint.sh",
    "container/supervisord.conf",
    "container/nginx.conf",
    "tests/acceptance/VERIFICATION.md",
)
FORBIDDEN_PARTS = {
    ".git",
    "node_modules",
    "target",
    "dist",
    "coverage",
    ".vite",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
}
SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
)


def main() -> int:
    missing = [item for item in REQUIRED if not (ROOT / item).is_file()]
    if missing:
        print("missing required files:", ", ".join(missing))
        return 1
    forbidden = [path for path in ROOT.rglob("*") if any(part in FORBIDDEN_PARTS for part in path.parts)]
    if forbidden:
        print("forbidden generated/dependency paths:", "\n".join(str(item.relative_to(ROOT)) for item in forbidden[:20]))
        return 1
    suspicious = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() in {".png", ".jpg", ".jpeg", ".zip", ".tar"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            suspicious.append(path.relative_to(ROOT))
    if suspicious:
        print("possible secrets:", "\n".join(map(str, suspicious)))
        return 1
    digest = hashlib.sha256((ROOT / "knowledge/sources/legal_sources.json").read_bytes()).hexdigest()
    print(f"delivery verification passed; knowledge_sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
