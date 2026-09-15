"""Import demo cases A/B/C through public Java /v1. Writes .t1-three-case-import.md."""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.adapters.case_bundle import load_case_bundle  # noqa: E402
from engine.adapters.t1_contract import (  # noqa: E402
    T1ContractError,
    build_t1_case_create,
    build_t1_fact_view,
    build_t1_module_state,
)

PLACEHOLDER = ROOT / ".t1-smoke-input.docx"
OUT = ROOT / ".t1-three-case-import.md"
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PDF_TYPE = "application/pdf"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import three-case demo via public /v1")
    parser.add_argument("--base-url", default=os.environ.get("LEXCYBER_BASE_URL", "http://127.0.0.1:18080"))
    parser.add_argument("--docs-dir", default=os.environ.get("LEXCYBER_DOCS_DIR", ""),
                        help="Local unzip directory; match archive_entry filenames")
    parser.add_argument("base_url_pos", nargs="?", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.base_url_pos:
        args.base_url = args.base_url_pos
    return args


def request(base: str, method: str, path: str, *, token: str | None = None, json_body: object | None = None,
            form: tuple[bytes, str, str, str] | None = None, idem: str | None = None) -> tuple[int, object]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if idem:
        headers["Idempotency-Key"] = idem
    data = None
    if json_body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
    elif form is not None:
        file_bytes, filename, content_type, role = form
        boundary = "----lexcyberImportBoundary"
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        parts = [
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"role\"\r\n\r\n{role}\r\n".encode(),
            (
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
                f"Content-Type: {content_type}\r\n\r\n"
            ).encode()
            + file_bytes
            + b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
        data = b"".join(parts)
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            body = json.loads(raw) if raw else {"message": str(exc)}
        except json.JSONDecodeError:
            body = {"message": raw.decode("utf-8", errors="replace")}
        return exc.code, body


def wait_ready(base: str) -> None:
    for _ in range(45):
        try:
            status, body = request(base, "GET", "/healthz")
            if status == 200 and (body or {}).get("status") == "ok":
                return
        except Exception:
            pass
        time.sleep(2)
    raise SystemExit(f"service not ready at {base}")


def poll_task(base: str, task_id: str, token: str) -> tuple[int, dict]:
    last: tuple[int, dict] = (0, {})
    for _ in range(60):
        status, body = request(base, "GET", f"/v1/tasks/{task_id}", token=token)
        last = (status, body if isinstance(body, dict) else {})
        if last[1].get("status") in {"completed", "failed", "timed_out", "rejected"}:
            return last
        time.sleep(2)
    return last


def content_type_for(filename: str) -> str:
    return PDF_TYPE if filename.lower().endswith(".pdf") else DOCX_TYPE


def resolve_material(docs_dir: Path | None, archive_entry: str) -> tuple[Path, bool]:
    name = Path(archive_entry.replace("\\", "/")).name
    candidates: list[Path] = []
    if docs_dir is not None:
        candidates.append(docs_dir / archive_entry.replace("\\", "/"))
        candidates.append(docs_dir / name)
        if docs_dir.is_dir():
            candidates.extend(path for path in docs_dir.rglob(name) if path.is_file())
    for path in candidates:
        if path.is_file():
            return path, False
    if PLACEHOLDER.is_file():
        return PLACEHOLDER, True
    raise SystemExit(
        f"missing material {archive_entry!r} under {docs_dir} and placeholder {PLACEHOLDER}"
    )


def case_create_payload(bundle: dict) -> dict:
    payload = build_t1_case_create(bundle)
    if not payload.get("asOfDate"):
        payload.pop("asOfDate", None)
    return payload


def authenticate(base: str) -> tuple[str, str, str]:
    username = os.environ.get("LEXCYBER_USERNAME", "").strip()
    password = os.environ.get("LEXCYBER_PASSWORD", "")
    if username and password:
        status, body = request(base, "POST", "/v1/auth/login",
                               json_body={"username": username, "password": password})
        if status == 200 and isinstance(body, dict) and body.get("token"):
            return body["token"], username, "login"
        status, body = request(base, "POST", "/v1/auth/register", json_body={
            "username": username, "password": password, "displayName": "T1 three-case import",
        })
        if status == 201 and isinstance(body, dict) and body.get("token"):
            return body["token"], username, "register"
        raise SystemExit(f"auth failed {status} {body}")
    suffix = random.randint(1000, 9999)
    username = f"t1import{suffix}"
    password = f"ImportPass{suffix}x"
    status, body = request(base, "POST", "/v1/auth/register", json_body={
        "username": username, "password": password, "displayName": "T1 three-case import",
    })
    if status != 201 or not isinstance(body, dict) or not body.get("token"):
        raise SystemExit(f"register failed {status} {body}")
    return body["token"], username, "register"


def import_case(base: str, token: str, code: str, docs_dir: Path | None) -> dict:
    bundle = load_case_bundle(code)
    status, created = request(base, "POST", "/v1/cases", token=token, json_body=case_create_payload(bundle))
    if status != 201 or not isinstance(created, dict) or not created.get("id"):
        raise SystemExit(f"create case {code} failed {status} {created}")
    case_id = created["id"]
    document_id_map: dict[str, str] = {}
    uploads: list[dict] = []
    for document in bundle.get("documents", []):
        if document.get("role") != "case_material":
            continue
        archive_entry = str(document.get("archive_entry") or document.get("title") or "")
        source, placeholder = resolve_material(docs_dir, archive_entry)
        filename = Path(archive_entry.replace("\\", "/")).name or source.name
        status, uploaded = request(
            base, "POST", f"/v1/cases/{case_id}/documents", token=token,
            form=(source.read_bytes(), filename, content_type_for(filename), "input"),
            idem=f"import-{code}-{document.get('id')}",
        )
        if status != 201 or not isinstance(uploaded, dict) or not uploaded.get("id"):
            raise SystemExit(f"upload {code} {document.get('id')} failed {status} {uploaded}")
        document_id_map[str(document["id"])] = uploaded["id"]
        parse_task_id = uploaded.get("parseTaskId")
        parse_status = None
        if parse_task_id:
            _, task = poll_task(base, str(parse_task_id), token)
            parse_status = task.get("status")
        uploads.append({
            "datasetDocumentId": document.get("id"),
            "documentId": uploaded["id"],
            "parseTaskId": parse_task_id,
            "parseStatus": parse_status,
            "archiveEntry": archive_entry,
            "placeholderUpload": placeholder,
            "sourcePath": str(source),
        })

    projected = build_t1_case_create(bundle, document_id_map)
    events = ((projected.get("metadata") or {}).get("relations") or {}).get("events") or []
    bindings: list[dict] = []
    for event in events:
        event_id = event.get("eventId")
        document_id = event.get("documentId")
        if not event_id or not document_id or document_id == "doc-pending-upload":
            continue
        body = {"documentId": document_id}
        if event.get("locator"):
            body["locator"] = event["locator"]
        status, bound = request(
            base, "PATCH",
            f"/v1/cases/{case_id}/metadata/relations/events/{event_id}/document",
            token=token, json_body=body,
        )
        bindings.append({"eventId": event_id, "documentId": document_id, "status": status})
        if status != 200:
            raise SystemExit(f"bind event {event_id} failed {status} {bound}")

    facts_note = "skipped"
    if document_id_map:
        try:
            fact_view = build_t1_fact_view(bundle, case_id=case_id, document_id_map=document_id_map, status="draft")
            status, facts = request(
                base, "PUT", f"/v1/cases/{case_id}/facts", token=token,
                json_body={"items": fact_view.get("items", [])},
            )
            if status != 200:
                raise SystemExit(f"put facts {code} failed {status} {facts}")
            facts_note = f"draft ({len(fact_view.get('items', []))} items)"
        except T1ContractError as exc:
            facts_note = f"skipped: {exc}"

    modules: dict[str, object] = {}
    for module in ("compliance", "conviction"):
        try:
            shell = build_t1_module_state(bundle, module, case_id)
        except T1ContractError as exc:
            modules[module] = f"skipped: {exc}"
            continue
        body = {
            "applicability": shell.get("applicability"),
            "content": shell.get("content") or {},
            "version": 0,
        }
        if shell.get("sourceVersion"):
            body["sourceVersion"] = shell["sourceVersion"]
        status, written = request(
            base, "PUT", f"/v1/cases/{case_id}/{module}", token=token, json_body=body,
        )
        if status != 200:
            raise SystemExit(f"put {module} {code} failed {status} {written}")
        modules[module] = {
            "status": written.get("status") if isinstance(written, dict) else None,
            "version": written.get("version") if isinstance(written, dict) else None,
            "applicability": written.get("applicability") if isinstance(written, dict) else None,
        }

    review_note = "skipped"
    conviction = modules.get("conviction")
    if isinstance(conviction, dict) and conviction.get("version") is not None:
        status, review = request(
            base, "POST", f"/v1/cases/{case_id}/reviews", token=token,
            json_body={
                "module": "conviction",
                "moduleState": "conviction",
                "moduleVersion": conviction.get("version"),
            },
        )
        if status == 201 and isinstance(review, dict):
            review_note = f"pending {review.get('id')}"
        else:
            review_note = f"skipped: {status} {review}"

    first = uploads[0] if uploads else {}
    return {
        "datasetCaseId": code,
        "t3BundleId": bundle.get("case_id"),
        "caseId": case_id,
        "documentId": first.get("documentId"),
        "parseTaskId": first.get("parseTaskId"),
        "uploads": uploads,
        "bindings": bindings,
        "facts": facts_note,
        "modules": modules,
        "review": review_note,
    }


def main() -> None:
    args = parse_args()
    base = args.base_url.rstrip("/")
    docs_dir = Path(args.docs_dir).expanduser() if args.docs_dir else None
    if docs_dir is not None and not docs_dir.is_dir():
        raise SystemExit(f"--docs-dir is not a directory: {docs_dir}")
    wait_ready(base)
    token, username, auth_mode = authenticate(base)
    imported = [import_case(base, token, code, docs_dir) for code in ("A", "B", "C")]
    lines = [
        "# T1 three-case import",
        "",
        f"- BaseUrl: {base}",
        f"- username: {username}",
        f"- authMode: {auth_mode}",
        f"- docsDir: {docs_dir or '(none; placeholder uploads allowed)'}",
        "",
    ]
    for item in imported:
        lines.append(
            f"- {item['datasetCaseId']}: caseId={item['caseId']} "
            f"documentId={item.get('documentId')} parseTaskId={item.get('parseTaskId')}"
        )
        print(
            f"{item['datasetCaseId']} caseId={item['caseId']} "
            f"documentId={item.get('documentId')} parseTaskId={item.get('parseTaskId')}"
        )
    lines.extend(["", "```json", json.dumps(imported, ensure_ascii=False, indent=2), "```", ""])
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"IMPORT_OK wrote {OUT}")


if __name__ == "__main__":
    main()
