"""Stage the eight real demo documents out of 法学材料/ into a flat docs dir.

Produces the files that import_three_case_demo.py --docs-dir expects:
  合成案例011（改）-输入材料.docx / -法学标注.docx   (case A)
  合成案例009（改）-输入材料.docx / -法学标注.docx   (case B)
  042输入材料新(1).docx / 042法学标注新(1).docx      (case B, converted)
  合成案例016-输入材料.docx / -法学标注.docx         (case C)

Usage:
  python deploy/stage_materials.py --src 法学材料 --out .tmp-legal-docs
"""

from __future__ import annotations

import argparse
import shutil
import sys
import zipfile
from pathlib import Path, PurePosixPath

CASE_ZIPS = ["演示案例A.zip", "演示案例B.zip", "演示案例C.zip"]
CONVERTED_042 = ["042输入材料新(1).docx", "042法学标注新(1).docx"]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--src", default="法学材料")
    p.add_argument("--out", default=".tmp-legal-docs")
    args = p.parse_args()
    src, out = Path(args.src), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    missing = []
    for z in CASE_ZIPS:
        zpath = src / z
        if not zpath.exists():
            missing.append(z)
            continue
        with zipfile.ZipFile(zpath) as f:
            for n in f.namelist():
                if n.lower().endswith(".docx"):
                    name = PurePosixPath(n.replace("\\", "/")).name
                    (out / name).write_bytes(f.read(n))
                    print("extracted:", name)
    for n in CONVERTED_042:
        fpath = src / n
        if not fpath.exists():
            missing.append(n)
            continue
        shutil.copy2(fpath, out / n)
        print("copied:", n)

    if missing:
        print("MISSING:", missing, file=sys.stderr)
        return 1
    print("staged ->", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
