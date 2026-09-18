"""Validate a case-import.v1 directory or ZIP without writing business data."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.import_package import validate_import_package  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a LexCyber case-import.v1 package")
    parser.add_argument("package", help="Package directory or .zip file")
    args = parser.parse_args()
    report = validate_import_package(args.package)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
