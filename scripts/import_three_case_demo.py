"""Import demo cases A/B/C through public Java /v1 with resumable client-side state."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.adapters.case_bundle import (  # noqa: E402
    load_case_bundle,
    load_case_dataset_index,
    validate_case_dataset,
)
from engine.adapters.t1_contract import (  # noqa: E402
    build_t1_case_create,
    build_t1_fact_view,
    build_t1_module_state,
)

PLACEHOLDER = ROOT / ".t1-smoke-input.docx"
OUT = ROOT / ".t1-three-case-import.md"
DEFAULT_CHECKPOINT = ROOT / ".t1-three-case-import.checkpoint.json"
CHECKPOINT_SCHEMA = "lexcyber.import-checkpoint.v2-uuid"
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PDF_TYPE = "application/pdf"
TERMINAL_TASK_STATUSES = {"completed", "failed", "timed_out", "rejected"}
DATE_PATTERN = re.compile(r"(?:\d{4}年\d{1,2}月(?:\d{1,2}日)?|\d{4}[\-/]\d{1,2}(?:[\-/]\d{1,2})?)")
AMOUNT_PATTERN = re.compile(
    r"(?:(?:人民币|RMB|CNY|USD|\$|¥|￥)\s*)?\d[\d,]*(?:\.\d+)?\s*(?:亿元|万元|万余元|元|dollars?)",
    re.IGNORECASE,
)
EXTRACT_LIMIT = 12


class ImportConflict(RuntimeError):
    """Raised when resuming would overwrite or ambiguously adopt existing data."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import three-case demo via public /v1")
    parser.add_argument("--base-url", default=os.environ.get("LEXCYBER_BASE_URL", "http://127.0.0.1:18080"))
    parser.add_argument(
        "--docs-dir",
        default=os.environ.get("LEXCYBER_DOCS_DIR", ""),
        help="Local unzip directory; match archive_entry filenames",
    )
    parser.add_argument(
        "--checkpoint",
        default=os.environ.get("LEXCYBER_IMPORT_CHECKPOINT", str(DEFAULT_CHECKPOINT)),
        help="Resumable mapping file; contains no token or password",
    )
    parser.add_argument(
        "--register-account",
        action="store_true",
        help="Register the explicitly configured LEXCYBER_USERNAME if login fails",
    )
    parser.add_argument(
        "--adopt-legacy",
        action="store_true",
        help="Explicitly adopt one legacy case matched by datasetCaseId+t3BundleId",
    )
    parser.add_argument(
        "--allow-placeholder",
        action="store_true",
        help="If a case_material file is missing, upload .t1-smoke-input.docx instead of failing",
    )
    parser.add_argument("base_url_pos", nargs="?", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.base_url_pos:
        args.base_url = args.base_url_pos
    return args


def request(
    base: str,
    method: str,
    path: str,
    *,
    token: str | None = None,
    json_body: object | None = None,
    form: tuple[bytes, str, str, str] | None = None,
    idem: str | None = None,
) -> tuple[int, object]:
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


def require_object(status: int, body: object, expected: int, operation: str) -> dict[str, Any]:
    if status != expected or not isinstance(body, dict):
        raise ImportConflict(f"{operation} failed: HTTP {status} {body}")
    return body


def wait_ready(base: str) -> None:
    for _ in range(45):
        try:
            status, body = request(base, "GET", "/healthz")
            if status == 200 and isinstance(body, dict) and body.get("status") == "ok":
                return
        except Exception:
            pass
        time.sleep(2)
    raise SystemExit(f"service not ready at {base}")


def poll_task(base: str, task_id: str, token: str) -> tuple[int, dict[str, Any]]:
    last: tuple[int, dict[str, Any]] = (0, {})
    for _ in range(60):
        status, body = request(base, "GET", f"/v1/tasks/{task_id}", token=token)
        last = (status, body if isinstance(body, dict) else {})
        if last[1].get("status") in TERMINAL_TASK_STATUSES:
            return last
        time.sleep(2)
    return last


def canonical_hash(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def content_type_for(filename: str) -> str:
    return PDF_TYPE if filename.lower().endswith(".pdf") else DOCX_TYPE


def _safe_archive_parts(archive_entry: str) -> tuple[str, ...]:
    normalized = archive_entry.replace("\\", "/")
    path = Path(normalized)
    if path.is_absolute() or path.drive or not normalized or any(part in {"", ".", ".."} for part in path.parts):
        raise ImportConflict(f"unsafe archive_entry: {archive_entry!r}")
    return tuple(path.parts)


def find_material(docs_dir: Path | None, archive_entry: str) -> Path | None:
    parts = _safe_archive_parts(archive_entry)
    name = parts[-1]
    candidates: list[Path] = []
    if docs_dir is not None:
        root = docs_dir.resolve()
        candidates.append(root.joinpath(*parts))
        candidates.append(root / name)
        if root.is_dir():
            candidates.extend(path for path in root.rglob(name) if path.is_file())
        for path in candidates:
            try:
                resolved = path.resolve(strict=True)
            except OSError:
                continue
            if resolved.is_relative_to(root) and resolved.is_file():
                return resolved
    return None


def resolve_material(docs_dir: Path | None, archive_entry: str, *, allow_placeholder: bool) -> tuple[Path, bool]:
    found = find_material(docs_dir, archive_entry)
    if found is not None:
        return found, False
    if allow_placeholder and PLACEHOLDER.is_file():
        return PLACEHOLDER, True
    location = str(docs_dir) if docs_dir else "(no --docs-dir)"
    raise FileNotFoundError(f"missing material {archive_entry!r} under {location}")


def list_case_materials() -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    index = load_case_dataset_index()
    for item in index.get("cases", []):
        bundle = load_case_bundle(str(item["case_code"]))
        for document in bundle.get("documents", []):
            if document.get("role") != "case_material":
                continue
            archive_entry = str(document.get("archive_entry") or document.get("title") or "")
            rows.append((str(item["case_code"]), str(document.get("id")), archive_entry))
    return rows


def preflight_materials(docs_dir: Path | None, *, allow_placeholder: bool) -> None:
    if allow_placeholder and not PLACEHOLDER.is_file():
        raise SystemExit(f"--allow-placeholder set but placeholder is missing: {PLACEHOLDER}")
    missing: list[str] = []
    for code, document_id, archive_entry in list_case_materials():
        if find_material(docs_dir, archive_entry) is not None:
            continue
        if allow_placeholder:
            continue
        missing.append(f"{code} {document_id} {archive_entry}")
    if not missing:
        return
    hint = "Pass --docs-dir with the unzipped case_material files, or --allow-placeholder for local smoke only."
    raise SystemExit("missing case_material:\n" + "\n".join(f"- {row}" for row in missing) + f"\n{hint}")


def _validate_importable_bundle(bundle: dict[str, Any], code: str) -> None:
    documents = {str(item["id"]): item for item in bundle.get("documents", [])}
    case_material_ids = {
        document_id for document_id, item in documents.items() if item.get("role") == "case_material"
    }
    for document_id in case_material_ids:
        archive_entry = str(documents[document_id].get("archive_entry") or "")
        _safe_archive_parts(archive_entry)
        if not archive_entry.lower().endswith((".pdf", ".docx")):
            raise SystemExit(f"unsupported case_material format {code} {document_id}: {archive_entry}")
    for evidence in bundle.get("evidence", []):
        document_id = str(evidence.get("document_id") or "")
        if document_id not in case_material_ids:
            raise SystemExit(
                f"evidence must reference an uploaded case_material {code} {evidence.get('id')}: {document_id}"
            )


def prepare_materials(docs_dir: Path | None, *, allow_placeholder: bool) -> dict[tuple[str, str], dict[str, Any]]:
    preflight_materials(docs_dir, allow_placeholder=allow_placeholder)
    prepared: dict[tuple[str, str], dict[str, Any]] = {}
    index = load_case_dataset_index()
    for item in index["cases"]:
        code = str(item["case_code"])
        bundle = load_case_bundle(code)
        _validate_importable_bundle(bundle, code)
        for document in bundle.get("documents", []):
            if document.get("role") != "case_material":
                continue
            archive_entry = str(document["archive_entry"])
            source, placeholder = resolve_material(docs_dir, archive_entry, allow_placeholder=allow_placeholder)
            file_bytes = source.read_bytes()
            actual_hash = hashlib.sha256(file_bytes).hexdigest()
            expected_hash = str(document["sha256"])
            if not placeholder and actual_hash != expected_hash:
                raise SystemExit(
                    f"material hash mismatch {code} {document['id']}: expected {expected_hash}, got {actual_hash}"
                )
            prepared[(code, str(document["id"]))] = {
                "bytes": file_bytes,
                "placeholder": placeholder,
                "sourceHash": actual_hash,
                "archiveEntry": archive_entry,
            }
    return prepared


def validate_import_dataset() -> dict[str, Any]:
    report = validate_case_dataset()
    if report.get("valid"):
        return report
    errors = list(report.get("errors") or [])
    for case in report.get("cases") or []:
        errors.extend(case.get("errors") or [])
    raise SystemExit("dataset validation failed:\n" + json.dumps(errors, ensure_ascii=False, indent=2))


def case_specs() -> list[dict[str, Any]]:
    index = load_case_dataset_index()
    return [
        {
            "producerId": str(index["producer_id"]),
            "datasetId": str(index["dataset_id"]),
            "revision": str(index["revision"]),
            "externalCaseId": str(item["external_case_id"]),
            "caseCode": str(item["case_code"]),
            "t3BundleId": str(item["case_id"]),
        }
        for item in index["cases"]
    ]


def dataset_digest() -> str:
    index = load_case_dataset_index()
    bundles = {str(item["external_case_id"]): load_case_bundle(str(item["case_code"])) for item in index["cases"]}
    return canonical_hash({"index": index, "bundles": bundles})


def case_create_payload(bundle: dict[str, Any], spec: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = build_t1_case_create(bundle)
    if not payload.get("asOfDate"):
        payload.pop("asOfDate", None)
    if spec:
        metadata = payload.setdefault("metadata", {})
        metadata.update(
            {
                "producerId": spec["producerId"],
                "externalCaseId": spec["externalCaseId"],
                "datasetId": spec["datasetId"],
                "datasetRevision": spec["revision"],
            }
        )
    return payload


def authenticate(base: str, *, register_account: bool = False) -> tuple[str, str, str]:
    username = os.environ.get("LEXCYBER_USERNAME", "").strip()
    password = os.environ.get("LEXCYBER_PASSWORD", "")
    if not username or not password:
        raise SystemExit("LEXCYBER_USERNAME and LEXCYBER_PASSWORD are required for stable owner-scoped imports")
    status, body = request(base, "POST", "/v1/auth/login", json_body={"username": username, "password": password})
    if status == 200 and isinstance(body, dict) and body.get("token"):
        return str(body["token"]), str(body.get("username") or username).lower(), "login"
    if not register_account:
        raise SystemExit(f"login failed {status} {body}; use --register-account only for an intentional first registration")
    status, body = request(
        base,
        "POST",
        "/v1/auth/register",
        json_body={"username": username, "password": password, "displayName": "T1 collaboration import"},
    )
    if status != 201 or not isinstance(body, dict) or not body.get("token"):
        raise SystemExit(f"register failed {status} {body}")
    return str(body["token"]), str(body.get("username") or username).lower(), "register"


def checkpoint_template(base: str, username: str) -> dict[str, Any]:
    index = load_case_dataset_index()
    return {
        "schemaVersion": CHECKPOINT_SCHEMA,
        "target": {"baseUrl": base, "username": username},
        "dataset": {
            "producerId": index["producer_id"],
            "datasetId": index["dataset_id"],
            "revision": index["revision"],
            "digest": dataset_digest(),
        },
        "cases": {},
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }


def load_checkpoint(path: Path, expected: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return expected
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"invalid checkpoint {path}: {exc}") from exc
    for field in ("schemaVersion", "target", "dataset"):
        if loaded.get(field) != expected.get(field):
            raise SystemExit(f"checkpoint {field} does not match this target/dataset: {path}")
    if not isinstance(loaded.get("cases"), dict):
        raise SystemExit(f"checkpoint cases must be an object: {path}")
    return loaded


def save_checkpoint(path: Path, checkpoint: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint["updatedAt"] = datetime.now(timezone.utc).isoformat()
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(checkpoint, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


@contextmanager
def checkpoint_lock(path: Path) -> Iterator[None]:
    """Hold an OS-managed non-blocking lock that is released after crashes."""

    lock_path = path.with_name(path.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    stream = lock_path.open("a+b")
    try:
        if os.name == "nt":
            import msvcrt

            if lock_path.stat().st_size == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise SystemExit(f"another import is using checkpoint: {path}") from exc
        else:
            import fcntl

            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise SystemExit(f"another import is using checkpoint: {path}") from exc
        yield
    finally:
        if os.name == "nt":
            import msvcrt

            try:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        else:
            import fcntl

            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        stream.close()


def paged_items(base: str, token: str, path: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page = 0
    seen_ids: set[str] = set()
    while True:
        separator = "&" if "?" in path else "?"
        status, body = request(base, "GET", f"{path}{separator}page={page}&size=100", token=token)
        payload = require_object(status, body, 200, f"list {path}")
        rows = payload.get("items")
        total = payload.get("total")
        if not isinstance(rows, list) or not isinstance(total, int) or total < 0:
            raise ImportConflict(f"invalid page response for {path}: {payload}")
        if not rows and len(items) < total:
            raise ImportConflict(f"incomplete page response for {path}: collected {len(items)} of {total}")
        for row in rows:
            if not isinstance(row, dict):
                raise ImportConflict(f"non-object item in {path}")
            resource_id = str(row.get("id", ""))
            if resource_id and resource_id in seen_ids:
                raise ImportConflict(f"duplicate resource id {resource_id} while paging {path}")
            if resource_id:
                seen_ids.add(resource_id)
            items.append(row)
        if len(items) >= total:
            return items
        page += 1


def _identity_matches(case: dict[str, Any], spec: dict[str, Any], *, legacy: bool = False) -> bool:
    metadata = case.get("metadata") if isinstance(case.get("metadata"), dict) else {}
    if legacy:
        return metadata.get("datasetCaseId") == spec["caseCode"] and metadata.get("t3BundleId") == spec["t3BundleId"]
    return metadata.get("producerId") == spec["producerId"] and metadata.get("externalCaseId") == spec["externalCaseId"]


def require_case_identity(case: dict[str, Any], spec: dict[str, Any], *, allow_legacy: bool = False) -> None:
    if not _identity_matches(case, spec) and not (allow_legacy and _identity_matches(case, spec, legacy=True)):
        raise ImportConflict(f"case {case.get('id')} identity does not match {spec['externalCaseId']}")
    metadata = case.get("metadata") if isinstance(case.get("metadata"), dict) else {}
    if metadata.get("datasetCaseId") != spec["caseCode"] or metadata.get("t3BundleId") != spec["t3BundleId"]:
        raise ImportConflict(f"case {case.get('id')} has conflicting dataset identity")
    if _identity_matches(case, spec):
        if metadata.get("datasetId") != spec["datasetId"] or metadata.get("datasetRevision") != spec["revision"]:
            raise ImportConflict(f"case {case.get('id')} belongs to another dataset revision")


def resolve_case(
    base: str,
    token: str,
    spec: dict[str, Any],
    bundle: dict[str, Any],
    case_state: dict[str, Any],
    checkpoint: dict[str, Any],
    checkpoint_path: Path,
    *,
    adopt_legacy: bool,
) -> tuple[dict[str, Any], str]:
    checkpoint_case_id = case_state.get("caseId")
    if checkpoint_case_id:
        status, body = request(base, "GET", f"/v1/cases/{checkpoint_case_id}", token=token)
        if status == 200 and isinstance(body, dict):
            require_case_identity(body, spec, allow_legacy=bool(case_state.get("legacyAdopted")))
            return body, "resumed_checkpoint"
        if status != 404:
            raise ImportConflict(f"get checkpoint case failed: HTTP {status} {body}")

    owned_cases = paged_items(base, token, "/v1/cases")
    exact = [case for case in owned_cases if _identity_matches(case, spec)]
    if len(exact) > 1:
        raise ImportConflict(f"multiple cases match {spec['producerId']}:{spec['externalCaseId']}")
    if exact:
        require_case_identity(exact[0], spec)
        case_state["caseId"] = exact[0]["id"]
        save_checkpoint(checkpoint_path, checkpoint)
        return exact[0], "resumed_server_identity"

    legacy = [case for case in owned_cases if _identity_matches(case, spec, legacy=True)]
    if legacy:
        if len(legacy) > 1 or not adopt_legacy:
            ids = [case.get("id") for case in legacy]
            raise ImportConflict(f"legacy case identity requires explicit --adopt-legacy: {ids}")
        require_case_identity(legacy[0], spec, allow_legacy=True)
        case_state["caseId"] = legacy[0]["id"]
        case_state["legacyAdopted"] = True
        save_checkpoint(checkpoint_path, checkpoint)
        return legacy[0], "adopted_legacy"

    case_state["phase"] = "case_create_planned"
    save_checkpoint(checkpoint_path, checkpoint)
    case_idempotency_key = "collab-case-" + hashlib.sha256(
        f"{spec['producerId']}:{spec['externalCaseId']}".encode("utf-8")
    ).hexdigest()
    status, body = request(
        base,
        "POST",
        "/v1/cases",
        token=token,
        json_body=case_create_payload(bundle, spec),
        idem=case_idempotency_key,
    )
    created = require_object(status, body, 201, f"create case {spec['caseCode']}")
    require_case_identity(created, spec)
    case_state["caseId"] = created["id"]
    case_state["phase"] = "case_created"
    save_checkpoint(checkpoint_path, checkpoint)
    return created, "created"


def stable_upload_key(spec: dict[str, Any], document_id: str) -> str:
    identity = f"{spec['producerId']}:{spec['externalCaseId']}:{document_id}"
    return "collab-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()


def upload_documents(
    base: str,
    token: str,
    spec: dict[str, Any],
    bundle: dict[str, Any],
    case_id: str,
    materials: dict[tuple[str, str], dict[str, Any]],
    case_state: dict[str, Any],
    checkpoint: dict[str, Any],
    checkpoint_path: Path,
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    document_states = case_state.setdefault("documents", {})
    document_id_map: dict[str, str] = {}
    report: list[dict[str, Any]] = []
    for document in bundle.get("documents", []):
        if document.get("role") != "case_material":
            continue
        external_document_id = str(document["id"])
        material = materials[(spec["caseCode"], external_document_id)]
        archive_entry = str(document["archive_entry"])
        filename = Path(archive_entry.replace("\\", "/")).name
        source_hash = str(material["sourceHash"])
        file_bytes = material["bytes"]
        state = document_states.setdefault(external_document_id, {})
        if state.get("sourceHash") not in (None, source_hash):
            raise ImportConflict(f"document source changed for {external_document_id}")
        state.update(
            {
                "sourceHash": source_hash,
                "filename": filename,
                "size": len(file_bytes),
                "idempotencyKey": stable_upload_key(spec, external_document_id),
                "state": state.get("state") or "upload_planned",
            }
        )
        save_checkpoint(checkpoint_path, checkpoint)

        uploaded: dict[str, Any] | None = None
        action = "uploaded"
        if state.get("documentId"):
            status, body = request(base, "GET", f"/v1/documents/{state['documentId']}", token=token)
            if status == 200 and isinstance(body, dict):
                uploaded = body
                action = "resumed_checkpoint"
            elif status != 404:
                raise ImportConflict(f"get document {state['documentId']} failed: HTTP {status} {body}")
        if uploaded is None:
            status, body = request(
                base,
                "POST",
                f"/v1/cases/{case_id}/documents",
                token=token,
                form=(file_bytes, filename, content_type_for(filename), "input"),
                idem=str(state["idempotencyKey"]),
            )
            uploaded = require_object(status, body, 201, f"upload {external_document_id}")
        if (
            uploaded.get("caseId") != case_id
            or uploaded.get("filename") != filename
            or uploaded.get("role") != "input"
            or uploaded.get("size") != len(file_bytes)
        ):
            raise ImportConflict(f"document replay does not match local material: {external_document_id}")

        state["documentId"] = uploaded["id"]
        state["parseTaskId"] = uploaded.get("parseTaskId")
        state["state"] = "stored"
        save_checkpoint(checkpoint_path, checkpoint)
        parse_status = uploaded.get("parseStatus")
        if state.get("parseTaskId") and parse_status not in TERMINAL_TASK_STATUSES:
            task_status, task = poll_task(base, str(state["parseTaskId"]), token)
            if task_status != 200:
                raise ImportConflict(f"poll parse task {state['parseTaskId']} failed: HTTP {task_status} {task}")
            parse_status = task.get("status")
        state["parseStatus"] = parse_status
        if parse_status != "completed":
            raise ImportConflict(f"document parse not completed for {external_document_id}: {parse_status}")
        state["state"] = "complete"
        save_checkpoint(checkpoint_path, checkpoint)
        document_id_map[external_document_id] = str(uploaded["id"])
        report.append(
            {
                "datasetDocumentId": external_document_id,
                "documentId": uploaded["id"],
                "parseTaskId": state.get("parseTaskId"),
                "parseStatus": parse_status,
                "action": action,
                "archiveEntry": archive_entry,
                "placeholderUpload": material["placeholder"],
                "sourceHash": source_hash,
            }
        )
    return document_id_map, report


def bind_events(
    base: str,
    token: str,
    bundle: dict[str, Any],
    case_id: str,
    document_id_map: dict[str, str],
    case_state: dict[str, Any],
    checkpoint: dict[str, Any],
    checkpoint_path: Path,
) -> list[dict[str, Any]]:
    projected = build_t1_case_create(bundle, document_id_map)
    expected_events = ((projected.get("metadata") or {}).get("relations") or {}).get("events") or []
    status, body = request(base, "GET", f"/v1/cases/{case_id}", token=token)
    current_case = require_object(status, body, 200, f"get case {case_id}")
    report: list[dict[str, Any]] = []
    binding_state = case_state.setdefault("bindings", {})
    for expected in expected_events:
        event_id = expected.get("eventId")
        document_id = expected.get("documentId")
        if not event_id or not document_id or document_id == "doc-pending-upload":
            continue
        current_events = (((current_case.get("metadata") or {}).get("relations") or {}).get("events") or [])
        matches = [event for event in current_events if isinstance(event, dict) and event.get("eventId") == event_id]
        if len(matches) != 1:
            raise ImportConflict(f"expected one server event {event_id}, found {len(matches)}")
        current = matches[0]
        current_document = current.get("documentId")
        expected_locator = expected.get("locator")
        if current_document == document_id:
            if expected_locator and current.get("locator") != expected_locator:
                raise ImportConflict(f"event locator conflict for {event_id}")
            action = "already_bound"
        elif current_document in (None, "", "doc-pending-upload"):
            update: dict[str, Any] = {"documentId": document_id}
            if expected_locator:
                update["locator"] = expected_locator
            patch_status, patch_body = request(
                base,
                "PATCH",
                f"/v1/cases/{case_id}/metadata/relations/events/{event_id}/document",
                token=token,
                json_body=update,
            )
            current_case = require_object(patch_status, patch_body, 200, f"bind event {event_id}")
            action = "bound"
        else:
            raise ImportConflict(f"event {event_id} is already bound to another document: {current_document}")
        binding_state[event_id] = {"documentId": document_id, "locator": expected_locator, "state": "complete"}
        save_checkpoint(checkpoint_path, checkpoint)
        report.append({"eventId": event_id, "documentId": document_id, "action": action})
    return report


def _parse_text_and_paragraphs(content: object) -> tuple[str, list[dict[str, Any]]]:
    if not isinstance(content, dict):
        return "", []
    raw_paragraphs = content.get("paragraphs") or []
    paragraphs = [item for item in raw_paragraphs if isinstance(item, dict)]
    text = content.get("text")
    if not isinstance(text, str) or not text.strip():
        text = "\n".join(str(item.get("text") or "") for item in paragraphs)
    return text, paragraphs


def _locator_for_value(value: str, paragraphs: list[dict[str, Any]]) -> str | None:
    for index, paragraph in enumerate(paragraphs):
        text = paragraph.get("text")
        if not isinstance(text, str) or value not in text:
            continue
        locator = paragraph.get("locator")
        if isinstance(locator, str) and locator:
            return locator
        number = paragraph.get("paragraph")
        return f"paragraph:{number if isinstance(number, int) else index + 1}"
    return None


def extract_candidates_from_parse_content(content: object, *, limit: int = EXTRACT_LIMIT) -> list[dict[str, Any]]:
    text, paragraphs = _parse_text_and_paragraphs(content)
    if not text.strip() or limit <= 0:
        return []
    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str | None]] = set()
    for kind, pattern in (("date", DATE_PATTERN), ("amount", AMOUNT_PATTERN)):
        for match in pattern.finditer(text):
            value = match.group()
            locator = _locator_for_value(value, paragraphs)
            key = (kind, value, locator)
            if key in seen:
                continue
            seen.add(key)
            items.append({"kind": kind, "value": value, "locator": locator})
            if len(items) >= limit:
                return items
    return items


def collect_parse_extracts(
    base: str,
    token: str,
    uploads: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    for upload in uploads:
        task_id = upload.get("parseTaskId")
        document_id = upload.get("documentId")
        if not task_id or not document_id:
            continue
        status, body = request(base, "GET", f"/v1/tasks/{task_id}/result", token=token)
        if status != 200 or not isinstance(body, dict):
            continue
        candidates = extract_candidates_from_parse_content(body.get("content"))
        collected.append(
            {
                "documentId": document_id,
                "parseTaskId": task_id,
                "candidateCount": len(candidates),
                "candidates": candidates,
            }
        )
    return collected


def extract_fact_items(extract_groups: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for group in extract_groups or []:
        document_id = str(group.get("documentId") or "")
        if not document_id:
            continue
        for index, candidate in enumerate(group.get("candidates") or []):
            if not isinstance(candidate, dict):
                continue
            value = str(candidate.get("value") or "").strip()
            kind = str(candidate.get("kind") or "span")
            if not value:
                continue
            items.append(
                {
                    "id": f"extracted-{document_id}-{index}",
                    "key": f"extracted_{kind}",
                    "value": value,
                    "locator": candidate.get("locator"),
                    "sourceDocumentId": document_id,
                    "verificationStatus": "candidate",
                }
            )
    return items


def apply_facts(
    base: str,
    token: str,
    bundle: dict[str, Any],
    case_id: str,
    document_id_map: dict[str, str],
    case_state: dict[str, Any],
    checkpoint: dict[str, Any],
    checkpoint_path: Path,
) -> dict[str, Any]:
    fact_view = build_t1_fact_view(bundle, case_id=case_id, document_id_map=document_id_map, status="draft")
    reviewed_items = fact_view.get("items", [])
    extract_items = extract_fact_items(case_state.get("extractCandidates"))
    combined_items = list(reviewed_items) + extract_items
    reviewed_hash = canonical_hash(reviewed_items)
    combined_hash = canonical_hash(combined_items)
    status, body = request(base, "GET", f"/v1/cases/{case_id}/facts", token=token)
    current = require_object(status, body, 200, "get facts")
    current_items = current.get("items") or []
    current_hash = canonical_hash(current_items)
    if current_hash in {combined_hash, reviewed_hash} and current.get("status") == "confirmed":
        action = "already_current"
        stored_hash = current_hash
    elif current_hash == combined_hash:
        action = "already_current"
        stored_hash = combined_hash
    elif current.get("status") == "draft" and not current_items:
        put_status, put_body = request(
            base,
            "PUT",
            f"/v1/cases/{case_id}/facts",
            token=token,
            json_body={"items": combined_items},
        )
        require_object(put_status, put_body, 200, "put facts")
        action = "written"
        stored_hash = combined_hash
    elif current.get("status") == "draft" and current_hash == reviewed_hash and extract_items:
        put_status, put_body = request(
            base,
            "PUT",
            f"/v1/cases/{case_id}/facts",
            token=token,
            json_body={"items": combined_items},
        )
        require_object(put_status, put_body, 200, "put facts")
        action = "attached_extract"
        stored_hash = combined_hash
    else:
        raise ImportConflict(f"existing facts differ for {case_id}; import will not overwrite them")
    case_state["facts"] = {"state": "complete", "contentHash": stored_hash, "action": action}
    save_checkpoint(checkpoint_path, checkpoint)
    return {
        "action": action,
        "status": current.get("status", "draft"),
        "itemCount": len(combined_items if action != "already_current" else current_items),
        "extractCount": len(extract_items),
    }


def apply_modules(
    base: str,
    token: str,
    bundle: dict[str, Any],
    case_id: str,
    case_state: dict[str, Any],
    checkpoint: dict[str, Any],
    checkpoint_path: Path,
) -> dict[str, Any]:
    report: dict[str, Any] = {}
    module_states = case_state.setdefault("modules", {})
    for module in ("compliance", "conviction"):
        shell = build_t1_module_state(bundle, module, case_id)
        expected = {
            "applicability": shell.get("applicability"),
            "content": shell.get("content") or {},
            "sourceVersion": shell.get("sourceVersion"),
        }
        status, body = request(base, "GET", f"/v1/cases/{case_id}/{module}", token=token)
        current = require_object(status, body, 200, f"get {module}")
        current_projection = {
            "applicability": current.get("applicability"),
            "content": current.get("content") or {},
            "sourceVersion": current.get("sourceVersion"),
        }
        same = canonical_hash(current_projection) == canonical_hash(expected)
        empty = current.get("status") == "draft" and current.get("version") == 0 and not current.get("content")
        if same and not current.get("factsStale"):
            action = "already_current"
            written = current
        elif current.get("status") == "confirmed":
            if not same:
                raise ImportConflict(f"confirmed {module} differs for {case_id}")
            if current.get("factsStale"):
                raise ImportConflict(
                    f"confirmed {module} is bound to stale facts for {case_id}; human review is required"
                )
            action = "already_confirmed"
            written = current
        elif empty or (same and current.get("factsStale")):
            update = dict(expected)
            update["version"] = current.get("version", 0)
            if update.get("sourceVersion") is None:
                update.pop("sourceVersion", None)
            put_status, put_body = request(
                base,
                "PUT",
                f"/v1/cases/{case_id}/{module}",
                token=token,
                json_body=update,
            )
            if put_status == 410:
                # v1.3 写层默认退役（MODULE_WRITE_RETIRED）；需 DEMO_IMPORT_ENABLED=true 才能写模块壳
                action = "skipped_write_retired"
                written = current
                report[module] = {
                    "action": action,
                    "warning": "module shell write retired; set DEMO_IMPORT_ENABLED=true to import legacy shells",
                }
                module_states[module] = {
                    "state": "skipped",
                    "contentHash": canonical_hash(expected),
                    "action": action,
                }
                save_checkpoint(checkpoint_path, checkpoint)
                continue
            written = require_object(put_status, put_body, 200, f"put {module}")
            action = "written" if empty else "refreshed_facts_snapshot"
        else:
            raise ImportConflict(f"existing draft {module} differs for {case_id}; import will not overwrite it")
        content_hash = canonical_hash(expected)
        module_states[module] = {
            "state": "complete",
            "contentHash": content_hash,
            "version": written.get("version"),
            "action": action,
        }
        save_checkpoint(checkpoint_path, checkpoint)
        report[module] = {
            "action": action,
            "status": written.get("status"),
            "version": written.get("version"),
            "applicability": written.get("applicability"),
            "factsStale": written.get("factsStale"),
        }
    return report


def ensure_conviction_review(
    base: str,
    token: str,
    case_id: str,
    conviction_version: int,
    case_state: dict[str, Any],
    checkpoint: dict[str, Any],
    checkpoint_path: Path,
) -> dict[str, Any]:
    review_state = case_state.setdefault("review", {})
    review_id = review_state.get("reviewId")
    if review_id:
        status, body = request(base, "GET", f"/v1/reviews/{review_id}", token=token)
        if status == 200 and isinstance(body, dict):
            if (
                body.get("caseId") != case_id
                or body.get("moduleState") != "conviction"
                or body.get("moduleVersion") != conviction_version
            ):
                raise ImportConflict(f"checkpoint review target mismatch: {review_id}")
            return {"action": "resumed_checkpoint", "reviewId": review_id, "status": body.get("status")}
        if status != 404:
            raise ImportConflict(f"get review {review_id} failed: HTTP {status} {body}")

    reviews = paged_items(base, token, "/v1/reviews?module=conviction")
    matches = [
        item
        for item in reviews
        if item.get("caseId") == case_id
        and item.get("moduleState") == "conviction"
        and item.get("moduleVersion") == conviction_version
    ]
    if len(matches) > 1:
        raise ImportConflict(f"multiple conviction reviews match {case_id} version {conviction_version}")
    if matches:
        review = matches[0]
        action = "already_opened"
    else:
        review_idempotency_key = "collab-review-" + hashlib.sha256(
            f"{case_id}:conviction:{conviction_version}".encode("utf-8")
        ).hexdigest()
        status, body = request(
            base,
            "POST",
            f"/v1/cases/{case_id}/reviews",
            token=token,
            json_body={
                "module": "conviction",
                "moduleState": "conviction",
                "moduleVersion": conviction_version,
            },
            idem=review_idempotency_key,
        )
        review = require_object(status, body, 201, "open conviction review")
        action = "opened"
    review_state.update(
        {
            "state": "complete",
            "reviewId": review.get("id"),
            "module": "conviction",
            "moduleVersion": conviction_version,
        }
    )
    save_checkpoint(checkpoint_path, checkpoint)
    return {"action": action, "reviewId": review.get("id"), "status": review.get("status")}


def import_case(
    base: str,
    token: str,
    code: str,
    docs_dir: Path | None,
    *,
    allow_placeholder: bool,
    spec: dict[str, Any] | None = None,
    materials: dict[tuple[str, str], dict[str, Any]] | None = None,
    checkpoint: dict[str, Any] | None = None,
    checkpoint_path: Path = DEFAULT_CHECKPOINT,
    adopt_legacy: bool = False,
) -> dict[str, Any]:
    del docs_dir, allow_placeholder  # Materials are resolved and hashed before any mutation.
    specs_by_code = {item["caseCode"]: item for item in case_specs()}
    spec = spec or specs_by_code[code]
    bundle = load_case_bundle(code)
    if materials is None:
        raise ImportConflict("materials must be prepared before import_case")
    if checkpoint is None:
        raise ImportConflict("checkpoint must be loaded before import_case")
    case_states = checkpoint.setdefault("cases", {})
    case_state = case_states.setdefault(
        spec["externalCaseId"],
        {
            "datasetCaseId": code,
            "t3BundleId": spec["t3BundleId"],
            "bundleHash": canonical_hash(bundle),
            "phase": "planned",
        },
    )
    if case_state.get("bundleHash") != canonical_hash(bundle):
        raise ImportConflict(f"bundle changed since checkpoint was created: {spec['externalCaseId']}")
    save_checkpoint(checkpoint_path, checkpoint)

    case, case_action = resolve_case(
        base,
        token,
        spec,
        bundle,
        case_state,
        checkpoint,
        checkpoint_path,
        adopt_legacy=adopt_legacy,
    )
    case_id = str(case["id"])
    document_id_map, uploads = upload_documents(
        base,
        token,
        spec,
        bundle,
        case_id,
        materials,
        case_state,
        checkpoint,
        checkpoint_path,
    )
    extracts = collect_parse_extracts(base, token, uploads)
    case_state["extractCandidates"] = extracts
    save_checkpoint(checkpoint_path, checkpoint)
    bindings = bind_events(
        base,
        token,
        bundle,
        case_id,
        document_id_map,
        case_state,
        checkpoint,
        checkpoint_path,
    )
    facts = apply_facts(
        base,
        token,
        bundle,
        case_id,
        document_id_map,
        case_state,
        checkpoint,
        checkpoint_path,
    )
    modules = apply_modules(base, token, bundle, case_id, case_state, checkpoint, checkpoint_path)
    conviction_version = modules["conviction"].get("version")
    if not isinstance(conviction_version, int):
        raise ImportConflict("conviction module did not return a version")
    review = ensure_conviction_review(
        base,
        token,
        case_id,
        conviction_version,
        case_state,
        checkpoint,
        checkpoint_path,
    )
    case_state["phase"] = "complete"
    save_checkpoint(checkpoint_path, checkpoint)
    first = uploads[0] if uploads else {}
    return {
        "status": "completed",
        "producerId": spec["producerId"],
        "externalCaseId": spec["externalCaseId"],
        "datasetCaseId": code,
        "t3BundleId": bundle.get("case_id"),
        "caseId": case_id,
        "caseAction": case_action,
        "documentId": first.get("documentId"),
        "parseTaskId": first.get("parseTaskId"),
        "uploads": uploads,
        "extractCandidates": extracts,
        "bindings": bindings,
        "facts": facts,
        "modules": modules,
        "review": review,
    }


def write_report(
    output: Path,
    *,
    base: str,
    username: str,
    auth_mode: str,
    docs_note: str,
    validation: dict[str, Any],
    imported: list[dict[str, Any]],
    checkpoint_path: Path,
) -> None:
    completed = sum(item.get("status") == "completed" for item in imported)
    failed = len(imported) - completed
    report = {
        "schemaVersion": "lexcyber.import-report.v1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "target": {"baseUrl": base, "authMode": auth_mode},
        "dataset": {
            "producerId": validation.get("producer_id"),
            "datasetId": validation.get("dataset_id"),
            "revision": validation.get("revision"),
        },
        "checkpoint": checkpoint_path.name,
        "documentsDirectory": docs_note,
        "summary": {"total": len(imported), "completed": completed, "failed": failed},
        "items": imported,
    }
    lines = [
        "# T1 collaboration import",
        "",
        f"- BaseUrl: {base}",
        "- account: configured import account",
        f"- authMode: {auth_mode}",
        f"- dataset: {validation.get('producer_id')} / {validation.get('dataset_id')} / {validation.get('revision')}",
        f"- docsDir: {docs_note}",
        f"- checkpoint: {checkpoint_path.name}",
        f"- result: completed={completed}, failed={failed}",
        "",
        "```json",
        json.dumps(report, ensure_ascii=False, indent=2),
        "```",
        "",
    ]
    output.write_text("\n".join(lines), encoding="utf-8")


def best_effort_save_checkpoint(path: Path, checkpoint: dict[str, Any]) -> str | None:
    try:
        save_checkpoint(path, checkpoint)
    except OSError as exc:
        message = f"checkpoint persistence failed: {exc}"
        print(message, file=sys.stderr)
        return message
    return None


def write_report_or_stderr(output: Path, **kwargs: Any) -> bool:
    try:
        write_report(output, **kwargs)
        return True
    except OSError as exc:
        fallback = {
            "schemaVersion": "lexcyber.import-report.v1",
            "status": "report_persistence_failed",
            "error": str(exc),
            "items": kwargs.get("imported", []),
        }
        print(json.dumps(fallback, ensure_ascii=False, indent=2), file=sys.stderr)
        return False


def main() -> int:
    args = parse_args()
    base = args.base_url.rstrip("/")
    docs_dir = Path(args.docs_dir).expanduser() if args.docs_dir else None
    checkpoint_path = Path(args.checkpoint).expanduser().resolve()
    if docs_dir is not None and not docs_dir.is_dir():
        raise SystemExit(f"--docs-dir is not a directory: {docs_dir}")

    validation = validate_import_dataset()
    allow_placeholder = bool(args.allow_placeholder)
    materials = prepare_materials(docs_dir, allow_placeholder=allow_placeholder)
    wait_ready(base)
    token, username, auth_mode = authenticate(base, register_account=bool(args.register_account))
    expected_checkpoint = checkpoint_template(base, username)

    with checkpoint_lock(checkpoint_path):
        checkpoint = load_checkpoint(checkpoint_path, expected_checkpoint)
        imported: list[dict[str, Any]] = []
        checkpoint_error = best_effort_save_checkpoint(checkpoint_path, checkpoint)
        specs = case_specs()
        if checkpoint_error:
            imported.extend(
                {
                    "status": "blocked",
                    "producerId": spec["producerId"],
                    "externalCaseId": spec["externalCaseId"],
                    "datasetCaseId": spec["caseCode"],
                    "t3BundleId": spec["t3BundleId"],
                    "error": checkpoint_error,
                }
                for spec in specs
            )
        else:
            for spec in specs:
                try:
                    result = import_case(
                        base,
                        token,
                        spec["caseCode"],
                        docs_dir,
                        allow_placeholder=allow_placeholder,
                        spec=spec,
                        materials=materials,
                        checkpoint=checkpoint,
                        checkpoint_path=checkpoint_path,
                        adopt_legacy=bool(args.adopt_legacy),
                    )
                except Exception as exc:  # Preserve a per-case report for transport, IO, and validation failures.
                    result = {
                        "status": "blocked",
                        "producerId": spec["producerId"],
                        "externalCaseId": spec["externalCaseId"],
                        "datasetCaseId": spec["caseCode"],
                        "t3BundleId": spec["t3BundleId"],
                        "error": str(exc),
                    }
                    state = checkpoint.setdefault("cases", {}).setdefault(spec["externalCaseId"], {})
                    state["phase"] = "blocked"
                    state["lastError"] = str(exc)
                    best_effort_save_checkpoint(checkpoint_path, checkpoint)
                imported.append(result)

        docs_note = "configured" if docs_dir else "(none)"
        if allow_placeholder:
            docs_note += "; placeholder uploads allowed"
        report_written = write_report_or_stderr(
            OUT,
            base=base,
            username=username,
            auth_mode=auth_mode,
            docs_note=docs_note,
            validation=validation,
            imported=imported,
            checkpoint_path=checkpoint_path,
        )
        for item in imported:
            print(
                f"{item['datasetCaseId']} status={item['status']} "
                f"caseId={item.get('caseId')} error={item.get('error', '')}"
            )
        if not report_written or any(item.get("status") != "completed" for item in imported):
            print(f"IMPORT_BLOCKED report={OUT if report_written else 'stderr'}")
            return 1
        print(f"IMPORT_OK wrote {OUT}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
