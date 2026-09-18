"""Restore the three-case demo state after a fresh import.

Run AFTER scripts/import_three_case_demo.py completes on a fresh stack.
Idempotent-ish: safe to re-run; already-confirmed facts are skipped by the
server, module rebind bumps version once per run.

Usage:
  LEXCYBER_USERNAME=demo_owner LEXCYBER_PASSWORD=... \
  python deploy/demo_restore.py --docs-dir .tmp-legal-docs
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = ROOT / ".t1-three-case-import.checkpoint.json"

# dataset case code -> actor used for the demo sentencing task
SENTENCING_ACTORS = {"A": "actor-a-feng", "B": "actor-b-huang", "C": "actor-c-jia"}
# dataset case code -> annotation filenames to upload from docs dir
ANNOTATIONS = {
    "A": ["合成案例011（改）-法学标注.docx"],
    "B": ["合成案例009（改）-法学标注.docx", "042法学标注新(1).docx"],
    "C": ["合成案例016-法学标注.docx"],
}
DATASET_CASE = {"A": "demo-case-a-helping", "B": "demo-case-b-proceeds", "C": "demo-case-c-unit-crossborder"}
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def req(base: str, path: str, method: str = "GET", body=None, token: str | None = None, form=None):
    r = urllib.request.Request(base + path, method=method)
    if token:
        r.add_header("Authorization", "Bearer " + token)
    data = None
    if form:
        file_bytes, filename, ctype, role = form
        bnd = uuid.uuid4().hex
        # 文件名按 UTF-8 原样写入 multipart 头（服务端不解码 %xx；quote() 会留下编码后的丑文件名）
        data = (
            f"--{bnd}\r\nContent-Disposition: form-data; name=\"role\"\r\n\r\n{role}\r\n"
            f"--{bnd}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
            f"Content-Type: {ctype}\r\n\r\n"
        ).encode("utf-8") + file_bytes + f"\r\n--{bnd}--\r\n".encode()
        r.add_header("Content-Type", f"multipart/form-data; boundary={bnd}")
    elif body is not None:
        data = json.dumps(body, ensure_ascii=False).encode()
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, data=data) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}


def load_case_ids(base: str, token: str) -> dict[str, str]:
    """Map dataset code -> server caseId via the import checkpoint."""
    if CHECKPOINT.exists():
        cp = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
        out = {}
        for external_id, state in (cp.get("cases") or {}).items():
            for code, ext in DATASET_CASE.items():
                if external_id == ext and state.get("caseId"):
                    out[code] = state["caseId"]
        if len(out) == 3:
            return out
    # fallback: ask the API
    status, body = req(base, "/v1/cases?page=0&size=50", token=token)
    if status != 200:
        raise SystemExit(f"cannot list cases: {status} {body}")
    out = {}
    for item in body.get("items", []):
        ext = str(item.get("externalCaseId") or "")
        for code, want in DATASET_CASE.items():
            if ext == want:
                out[code] = item["id"]
    if len(out) != 3:
        raise SystemExit(f"cannot resolve all three demo cases: {out}")
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", default=os.environ.get("LEXCYBER_BASE_URL", "http://127.0.0.1:18080"))
    p.add_argument("--docs-dir", default=os.environ.get("LEXCYBER_DOCS_DIR", ".tmp-legal-docs"))
    p.add_argument("--skip-sentencing", action="store_true")
    args = p.parse_args()
    base, docs_dir = args.base_url.rstrip("/"), Path(args.docs_dir)
    user = os.environ.get("LEXCYBER_USERNAME", "demo_owner")
    pw = os.environ.get("LEXCYBER_PASSWORD", "")
    if not pw:
        raise SystemExit("LEXCYBER_PASSWORD is required")

    status, body = req(base, "/v1/auth/login", "POST", {"username": user, "password": pw})
    if status != 200:
        raise SystemExit(f"login failed: {status} {body}")
    token = body["token"]
    cases = load_case_ids(base, token)
    print("cases:", cases)

    for code, cid in cases.items():
        s, b = req(base, f"/v1/cases/{cid}/facts/confirm", "POST", {}, token)
        print(code, "facts confirm:", s, b.get("status"))

    for code, cid in cases.items():
        for m in ("compliance", "conviction"):
            s, cur = req(base, f"/v1/cases/{cid}/{m}", token=token)
            if s != 200:
                print(code, m, "GET failed", s)
                continue
            s2, b2 = req(base, f"/v1/cases/{cid}/{m}", "PUT", {
                "applicability": cur.get("applicability"),
                "content": cur.get("content"),
                "sourceVersion": cur.get("sourceVersion"),
                "version": cur.get("version"),
            }, token)
            print(code, m, "rebind:", s2, "v" + str(b2.get("version")))

    s, rl = req(base, "/v1/reviews?archiveStatus=open&size=100", token=token)
    current_version = {}
    for code, cid in cases.items():
        s2, cur = req(base, f"/v1/cases/{cid}/conviction", token=token)
        current_version[cid] = cur.get("version")
    for it in rl.get("items", []):
        stale = it.get("module") == "conviction" and it.get("moduleVersion") != current_version.get(it.get("caseId"))
        if stale and it.get("status") == "pending":
            s2, _ = req(base, f"/v1/reviews/{it['id']}/archive", "POST", {}, token)
            print("archived stale review", it["id"], s2)

    open_by_case = {}
    for it in rl.get("items", []):
        if it.get("module") == "conviction" and it.get("status") == "pending":
            open_by_case.setdefault(it.get("caseId"), it.get("moduleVersion"))
    for code, cid in cases.items():
        if open_by_case.get(cid) == current_version.get(cid):
            print(code, "conviction review already open at current version, skipped")
            continue
        s, b = req(base, f"/v1/cases/{cid}/reviews", "POST",
                   {"module": "conviction", "moduleState": "conviction"}, token)
        print(code, "open conviction review:", s, b.get("id"))

    for code, files in ANNOTATIONS.items():
        for fn in files:
            fpath = docs_dir / fn
            if not fpath.exists():
                print(code, fn, "MISSING in", docs_dir)
                continue
            s, b = req(base, f"/v1/cases/{cases[code]}/documents", "POST",
                       token=token, form=(fpath.read_bytes(), fn, DOCX_MIME, "annotation"))
            print(code, fn, "upload:", s, b.get("id"))

    if not args.skip_sentencing:
        for code, cid in cases.items():
            actor = SENTENCING_ACTORS[code]
            s, b = req(base, "/v1/tasks", "POST", {
                "query": f"量刑分析 {actor}",
                "caseId": cid,
                "metadata": {"taskType": "sentencing.calculate",
                             "sentencing": {"datasetCaseId": code, "actorId": actor}},
            }, token)
            tid = b.get("id")
            print(code, "sentencing task:", s, tid)
            if s not in (200, 201, 202) or not tid:
                continue
            for _ in range(40):
                time.sleep(2)
                s2, t2 = req(base, f"/v1/tasks/{tid}", token=token)
                if t2.get("status") in ("completed", "failed", "waiting_review"):
                    break
            print(code, "->", t2.get("status"), (t2.get("error") or "")[:120])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
