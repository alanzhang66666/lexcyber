from __future__ import annotations

import json
from pathlib import Path
from sys import path as import_path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in import_path:
    import_path.insert(0, str(REPOSITORY_ROOT))

from engine.adapters.case_bundle import load_case_bundle, validate_case_dataset  # noqa: E402
from engine.adapters.t1_contract import build_t1_case_create  # noqa: E402


def main() -> int:
    report = validate_case_dataset()
    report["t1_case_create"] = {
        code: build_t1_case_create(load_case_bundle(code)) for code in ("A", "B", "C")
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
