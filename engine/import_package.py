"""Fail-closed reader and validator for directory or ZIP case-import.v1 packages."""
from __future__ import annotations

import copy
import hashlib
import io
import json
import math
import stat
import zipfile
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, Iterable

from jsonschema import Draft202012Validator, FormatChecker

PACKAGE_SCHEMA_VERSION = "lexcyber.case-import.v1"
CANONICALIZATION_VERSION = "lexcyber.case-import.c14n.v1"
MANIFEST_NAME = "case-import.json"
PACKAGE_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "contracts" / "schemas" / "case-import-package-v1.schema.json"
BUNDLE_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "contracts" / "schemas" / "collaboration-case-bundle.schema.json"
DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PDF_MEDIA_TYPE = "application/pdf"
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_PAYLOAD_BYTES = 10 * 1024 * 1024
MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_PACKAGE_BYTES = 512 * 1024 * 1024
MAX_PACKAGE_ENTRIES = 10000
MAX_COMPRESSION_RATIO = 100
DIGEST_PLACEHOLDER = "0" * 64


@dataclass(frozen=True)
class ImportPackageIssue:
    code: str
    path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}


@dataclass(frozen=True)
class LoadedImportPackage:
    source: Path
    source_kind: str
    manifest: dict[str, Any]
    payloads: dict[str, dict[str, Any]]
    package_digest: str
    item_count: int
    file_count: int
    total_bytes: int


class ImportPackageValidationError(ValueError):
    def __init__(self, issues: Iterable[ImportPackageIssue]) -> None:
        self.issues = tuple(issues)
        summary = "; ".join(f"{item.code} at {item.path}: {item.message}" for item in self.issues[:5])
        super().__init__(summary or "invalid import package")


class _DuplicateJsonKey(ValueError):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(f"duplicate object key: {key}")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise ValueError(f"non-finite JSON number is not allowed: {value}")


def _read_json_bytes(data: bytes, logical_path: str) -> dict[str, Any]:
    try:
        decoded = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ImportPackageValidationError(
            [ImportPackageIssue("INVALID_UTF8", logical_path, "JSON must be UTF-8")]
        ) from exc
    try:
        parsed = json.loads(
            decoded,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite,
        )
    except (json.JSONDecodeError, _DuplicateJsonKey, ValueError) as exc:
        raise ImportPackageValidationError(
            [ImportPackageIssue("INVALID_JSON", logical_path, str(exc))]
        ) from exc
    if not isinstance(parsed, dict):
        raise ImportPackageValidationError(
            [ImportPackageIssue("INVALID_JSON_ROOT", logical_path, "JSON root must be an object")]
        )
    return parsed


def _json_path(prefix: str, parts: Iterable[Any]) -> str:
    result = prefix
    for part in parts:
        result += f"[{part}]" if isinstance(part, int) else f".{part}"
    return result


def _schema_issues(instance: Any, schema_path: Path, prefix: str) -> list[ImportPackageIssue]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        ImportPackageIssue("SCHEMA_VALIDATION_FAILED", _json_path(prefix, error.absolute_path), error.message)
        for error in sorted(validator.iter_errors(instance), key=lambda item: [str(part) for part in item.absolute_path])
    ]


def normalize_package_path(value: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise ValueError("path must be a non-empty POSIX relative path")
    if value.startswith(("/", "//")) or (len(value) >= 2 and value[1] == ":"):
        raise ValueError("absolute, UNC, and drive-qualified paths are forbidden")
    path = PurePosixPath(value)
    if any(part in {"", ".", ".."} for part in path.parts) or str(path) != value or value.endswith("/"):
        raise ValueError("path must be normalized and cannot contain dot segments")
    return value


def canonical_manifest_bytes(manifest: dict[str, Any]) -> bytes:
    projection = copy.deepcopy(manifest)
    digest = projection.get("package_digest")
    if not isinstance(digest, dict):
        raise ValueError("package_digest is required")
    digest["value"] = DIGEST_PLACEHOLDER
    items = projection.get("items")
    if not isinstance(items, list):
        raise ValueError("items must be an array")
    for item in items:
        if isinstance(item, dict) and isinstance(item.get("files"), list):
            item["files"] = sorted(item["files"], key=lambda value: str(value.get("file_id", "")))
    projection["items"] = sorted(items, key=lambda value: str(value.get("item_id", "")))
    return json.dumps(
        projection,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def calculate_package_digest(manifest: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_manifest_bytes(manifest)).hexdigest()


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _check_descriptor(data: bytes, descriptor: dict[str, Any], path: str) -> list[ImportPackageIssue]:
    issues: list[ImportPackageIssue] = []
    expected_size = descriptor.get("size")
    if expected_size != len(data):
        issues.append(ImportPackageIssue("SIZE_MISMATCH", path, f"expected {expected_size}, got {len(data)}"))
    expected_hash = descriptor.get("sha256")
    actual_hash = _hash_bytes(data)
    if expected_hash != actual_hash:
        issues.append(ImportPackageIssue("HASH_MISMATCH", path, f"expected {expected_hash}, got {actual_hash}"))
    return issues


def _check_document_media(data: bytes, descriptor: dict[str, Any], path: str) -> list[ImportPackageIssue]:
    media_type = descriptor.get("media_type")
    suffix = PurePosixPath(path).suffix.lower()
    if media_type == PDF_MEDIA_TYPE:
        if suffix != ".pdf" or not data.startswith(b"%PDF-"):
            return [ImportPackageIssue("MEDIA_TYPE_MISMATCH", path, "declared PDF is not a PDF file")]
        return []
    if media_type == DOCX_MEDIA_TYPE:
        if suffix != ".docx":
            return [ImportPackageIssue("MEDIA_TYPE_MISMATCH", path, "DOCX media type requires .docx")]
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = set(archive.namelist())
        except (zipfile.BadZipFile, OSError):
            return [ImportPackageIssue("MEDIA_TYPE_MISMATCH", path, "declared DOCX is not a valid ZIP container")]
        required = {"[Content_Types].xml", "word/document.xml"}
        if not required.issubset(names):
            return [ImportPackageIssue("MEDIA_TYPE_MISMATCH", path, "DOCX is missing required package entries")]
        return []
    return [ImportPackageIssue("UNSUPPORTED_MEDIA_TYPE", path, str(media_type))]


class _PackageSource(AbstractContextManager["_PackageSource"]):
    kind: str

    def names(self) -> set[str]:
        raise NotImplementedError

    def read(self, logical_path: str, limit: int) -> bytes:
        raise NotImplementedError


class _DirectorySource(_PackageSource):
    kind = "directory"

    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError("package source is not a directory")
        self._names: set[str] = set()
        casefolded: set[str] = set()
        total = 0
        for candidate in self.root.rglob("*"):
            if candidate.is_symlink():
                raise ValueError(f"symlink entries are forbidden: {candidate}")
            if not candidate.is_file():
                continue
            resolved = candidate.resolve(strict=True)
            if not resolved.is_relative_to(self.root):
                raise ValueError(f"package entry escapes root: {candidate}")
            name = normalize_package_path(candidate.relative_to(self.root).as_posix())
            folded = name.casefold()
            if name in self._names or folded in casefolded:
                raise ValueError(f"duplicate or case-conflicting package path: {name}")
            self._names.add(name)
            casefolded.add(folded)
            total += candidate.stat().st_size
            if len(self._names) > MAX_PACKAGE_ENTRIES or total > MAX_PACKAGE_BYTES:
                raise ValueError("package exceeds entry or total size limit")

    def names(self) -> set[str]:
        return set(self._names)

    def read(self, logical_path: str, limit: int) -> bytes:
        normalized = normalize_package_path(logical_path)
        target = self.root.joinpath(*PurePosixPath(normalized).parts)
        if target.is_symlink():
            raise ValueError(f"symlink entries are forbidden: {logical_path}")
        resolved = target.resolve(strict=True)
        if not resolved.is_relative_to(self.root) or not resolved.is_file():
            raise ValueError(f"package path is not a regular file: {logical_path}")
        with resolved.open("rb") as stream:
            return _read_limited(stream, limit)

    def __exit__(self, *args: object) -> None:
        return None


class _ZipSource(_PackageSource):
    kind = "zip"

    def __init__(self, archive_path: Path) -> None:
        self.archive = zipfile.ZipFile(archive_path)
        self._entries: dict[str, zipfile.ZipInfo] = {}
        casefolded: set[str] = set()
        total = 0
        try:
            for info in self.archive.infolist():
                if info.is_dir():
                    continue
                name = normalize_package_path(info.filename)
                folded = name.casefold()
                if name in self._entries or folded in casefolded:
                    raise ValueError(f"duplicate or case-conflicting ZIP path: {name}")
                unix_mode = (info.external_attr >> 16) & 0xFFFF
                file_type = stat.S_IFMT(unix_mode)
                if file_type not in {0, stat.S_IFREG}:
                    raise ValueError(f"ZIP special entries are forbidden: {name}")
                if info.flag_bits & 0x1:
                    raise ValueError(f"encrypted ZIP entries are forbidden: {name}")
                if info.file_size > MAX_FILE_BYTES and name != MANIFEST_NAME:
                    raise ValueError(f"ZIP entry exceeds per-file limit: {name}")
                ratio = math.inf if info.compress_size == 0 and info.file_size else info.file_size / max(info.compress_size, 1)
                if ratio > MAX_COMPRESSION_RATIO:
                    raise ValueError(f"ZIP compression ratio exceeds limit: {name}")
                self._entries[name] = info
                casefolded.add(folded)
                total += info.file_size
                if len(self._entries) > MAX_PACKAGE_ENTRIES or total > MAX_PACKAGE_BYTES:
                    raise ValueError("ZIP exceeds entry or total size limit")
        except Exception:
            self.archive.close()
            raise

    def names(self) -> set[str]:
        return set(self._entries)

    def read(self, logical_path: str, limit: int) -> bytes:
        normalized = normalize_package_path(logical_path)
        info = self._entries.get(normalized)
        if info is None:
            raise FileNotFoundError(normalized)
        with self.archive.open(info, "r") as stream:
            return _read_limited(stream, limit)

    def __exit__(self, *args: object) -> None:
        self.archive.close()
        return None


def _read_limited(stream: BinaryIO, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = stream.read(min(1024 * 1024, limit + 1 - total))
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise ValueError(f"entry exceeds {limit} byte limit")
        chunks.append(chunk)
    return b"".join(chunks)


def _open_source(path: Path) -> _PackageSource:
    if path.is_dir():
        return _DirectorySource(path)
    if path.is_file() and path.suffix.lower() == ".zip":
        return _ZipSource(path)
    raise ValueError("import package must be a directory or .zip file")


def _validate_manifest_semantics(manifest: dict[str, Any]) -> list[ImportPackageIssue]:
    issues: list[ImportPackageIssue] = []
    item_ids: set[str] = set()
    external_ids: set[str] = set()
    file_ids: set[str] = set()
    paths: set[str] = set()
    casefolded_paths: set[str] = set()
    for index, item in enumerate(manifest.get("items", [])):
        item_path = f"$.items[{index}]"
        item_id = str(item.get("item_id", ""))
        external_id = str(item.get("external_case_id", ""))
        if item_id in item_ids:
            issues.append(ImportPackageIssue("DUPLICATE_ITEM_ID", f"{item_path}.item_id", item_id))
        if external_id in external_ids:
            issues.append(ImportPackageIssue("DUPLICATE_EXTERNAL_CASE_ID", f"{item_path}.external_case_id", external_id))
        item_ids.add(item_id)
        external_ids.add(external_id)
        descriptors = [("payload", item.get("payload"))]
        descriptors.extend((f"files[{position}]", value) for position, value in enumerate(item.get("files", [])))
        for descriptor_name, descriptor in descriptors:
            if not isinstance(descriptor, dict):
                continue
            descriptor_path = f"{item_path}.{descriptor_name}"
            path_value = descriptor.get("path")
            try:
                normalized = normalize_package_path(path_value)
            except (TypeError, ValueError) as exc:
                issues.append(ImportPackageIssue("UNSAFE_PATH", f"{descriptor_path}.path", str(exc)))
                continue
            folded = normalized.casefold()
            if normalized in paths or folded in casefolded_paths:
                issues.append(ImportPackageIssue("DUPLICATE_PATH", f"{descriptor_path}.path", normalized))
            paths.add(normalized)
            casefolded_paths.add(folded)
        document_ids: set[str] = set()
        for position, descriptor in enumerate(item.get("files", [])):
            if not isinstance(descriptor, dict):
                continue
            file_id = str(descriptor.get("file_id", ""))
            document_id = str(descriptor.get("document_id", ""))
            if file_id in file_ids:
                issues.append(ImportPackageIssue("DUPLICATE_FILE_ID", f"{item_path}.files[{position}].file_id", file_id))
            if document_id in document_ids:
                issues.append(
                    ImportPackageIssue(
                        "DUPLICATE_DOCUMENT_ID",
                        f"{item_path}.files[{position}].document_id",
                        document_id,
                    )
                )
            file_ids.add(file_id)
            document_ids.add(document_id)
    try:
        calculated = calculate_package_digest(manifest)
    except (TypeError, ValueError) as exc:
        issues.append(ImportPackageIssue("INVALID_CANONICAL_MANIFEST", "$.package_digest", str(exc)))
    else:
        declared = (manifest.get("package_digest") or {}).get("value")
        if declared != calculated:
            issues.append(ImportPackageIssue("PACKAGE_DIGEST_MISMATCH", "$.package_digest.value", f"expected {calculated}, got {declared}"))
    return issues


def _validate_bundle_bindings(
    manifest_item: dict[str, Any], bundle: dict[str, Any], prefix: str
) -> list[ImportPackageIssue]:
    issues: list[ImportPackageIssue] = []
    external_case_id = manifest_item.get("external_case_id")
    if bundle.get("case_id") != external_case_id:
        issues.append(
            ImportPackageIssue(
                "CASE_IDENTITY_MISMATCH",
                f"{prefix}.payload",
                f"bundle case_id {bundle.get('case_id')} does not match {external_case_id}",
            )
        )
    bundle_document_rows = [
        document
        for document in bundle.get("documents", [])
        if isinstance(document, dict) and document.get("id")
    ]
    manifest_file_rows = [
        descriptor
        for descriptor in manifest_item.get("files", [])
        if isinstance(descriptor, dict) and descriptor.get("document_id")
    ]
    bundle_document_ids = [str(document["id"]) for document in bundle_document_rows]
    manifest_document_ids = [str(descriptor["document_id"]) for descriptor in manifest_file_rows]
    if len(set(bundle_document_ids)) != len(bundle_document_ids):
        issues.append(
            ImportPackageIssue("DUPLICATE_BUNDLE_DOCUMENT_ID", f"{prefix}.payload.documents", "document ids must be unique")
        )
    if len(set(manifest_document_ids)) != len(manifest_document_ids):
        issues.append(
            ImportPackageIssue("DUPLICATE_DOCUMENT_ID", f"{prefix}.files", "document ids must be unique within an item")
        )
    bundle_documents = {str(document["id"]): document for document in bundle_document_rows}
    manifest_files = {str(descriptor["document_id"]): descriptor for descriptor in manifest_file_rows}
    if set(bundle_documents) != set(manifest_files):
        issues.append(
            ImportPackageIssue(
                "DOCUMENT_SET_MISMATCH",
                f"{prefix}.files",
                f"bundle documents {sorted(bundle_documents)} do not match manifest {sorted(manifest_files)}",
            )
        )
    for document_id in sorted(set(bundle_documents) & set(manifest_files)):
        document = bundle_documents[document_id]
        descriptor = manifest_files[document_id]
        if document.get("role") != descriptor.get("role"):
            issues.append(ImportPackageIssue("DOCUMENT_ROLE_MISMATCH", f"{prefix}.files", document_id))
        if document.get("sha256") != descriptor.get("sha256"):
            issues.append(ImportPackageIssue("DOCUMENT_HASH_MISMATCH", f"{prefix}.files", document_id))
    material_ids = {
        document_id for document_id, document in bundle_documents.items() if document.get("role") == "case_material"
    }
    for position, evidence in enumerate(bundle.get("evidence", [])):
        if isinstance(evidence, dict) and evidence.get("document_id") not in material_ids:
            issues.append(
                ImportPackageIssue(
                    "EVIDENCE_NOT_CASE_MATERIAL",
                    f"{prefix}.payload.evidence[{position}].document_id",
                    str(evidence.get("document_id")),
                )
            )
    return issues


def load_import_package(path: str | Path) -> LoadedImportPackage:
    source_path = Path(path).expanduser().resolve()
    issues: list[ImportPackageIssue] = []
    try:
        source_context = _open_source(source_path)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        raise ImportPackageValidationError(
            [ImportPackageIssue("INVALID_PACKAGE_SOURCE", "$", str(exc))]
        ) from exc
    with source_context as source:
        names = source.names()
        if MANIFEST_NAME not in names:
            raise ImportPackageValidationError(
                [ImportPackageIssue("MANIFEST_MISSING", "$", f"missing {MANIFEST_NAME}")]
            )
        try:
            manifest = _read_json_bytes(source.read(MANIFEST_NAME, MAX_MANIFEST_BYTES), MANIFEST_NAME)
        except (OSError, ValueError) as exc:
            raise ImportPackageValidationError(
                [ImportPackageIssue("MANIFEST_READ_FAILED", MANIFEST_NAME, str(exc))]
            ) from exc
        issues.extend(_schema_issues(manifest, PACKAGE_SCHEMA_PATH, "$"))
        if issues:
            raise ImportPackageValidationError(issues)
        issues.extend(_validate_manifest_semantics(manifest))
        declared_paths = {MANIFEST_NAME}
        for item in manifest["items"]:
            declared_paths.add(item["payload"]["path"])
            declared_paths.update(descriptor["path"] for descriptor in item["files"])
        undeclared = sorted(names - declared_paths)
        missing = sorted(declared_paths - names)
        issues.extend(ImportPackageIssue("UNDECLARED_ENTRY", entry, "entry is not declared") for entry in undeclared)
        issues.extend(ImportPackageIssue("DECLARED_ENTRY_MISSING", entry, "declared entry is missing") for entry in missing)
        payloads: dict[str, dict[str, Any]] = {}
        total_bytes = 0
        file_count = 0
        if not missing:
            for position, item in enumerate(manifest["items"]):
                prefix = f"$.items[{position}]"
                payload_descriptor = item["payload"]
                payload_path = payload_descriptor["path"]
                try:
                    payload_bytes = source.read(payload_path, MAX_PAYLOAD_BYTES)
                except (OSError, ValueError) as exc:
                    issues.append(ImportPackageIssue("ENTRY_READ_FAILED", payload_path, str(exc)))
                    continue
                total_bytes += len(payload_bytes)
                issues.extend(_check_descriptor(payload_bytes, payload_descriptor, payload_path))
                try:
                    bundle = _read_json_bytes(payload_bytes, payload_path)
                except ImportPackageValidationError as exc:
                    issues.extend(exc.issues)
                    continue
                issues.extend(_schema_issues(bundle, BUNDLE_SCHEMA_PATH, f"{prefix}.payload"))
                payloads[item["item_id"]] = bundle
                issues.extend(_validate_bundle_bindings(item, bundle, prefix))
                for descriptor in item["files"]:
                    file_path = descriptor["path"]
                    try:
                        data = source.read(file_path, MAX_FILE_BYTES)
                    except (OSError, ValueError) as exc:
                        issues.append(ImportPackageIssue("ENTRY_READ_FAILED", file_path, str(exc)))
                        continue
                    total_bytes += len(data)
                    file_count += 1
                    if total_bytes > MAX_PACKAGE_BYTES:
                        issues.append(ImportPackageIssue("PACKAGE_TOO_LARGE", "$", str(total_bytes)))
                        break
                    issues.extend(_check_descriptor(data, descriptor, file_path))
                    issues.extend(_check_document_media(data, descriptor, file_path))
        if issues:
            raise ImportPackageValidationError(issues)
        return LoadedImportPackage(
            source=source_path,
            source_kind=source.kind,
            manifest=manifest,
            payloads=payloads,
            package_digest=calculate_package_digest(manifest),
            item_count=len(manifest["items"]),
            file_count=file_count,
            total_bytes=total_bytes,
        )


def validate_import_package(path: str | Path) -> dict[str, Any]:
    try:
        package = load_import_package(path)
    except ImportPackageValidationError as exc:
        return {"valid": False, "errors": [item.as_dict() for item in exc.issues]}
    return {
        "valid": True,
        "schemaVersion": package.manifest["schema_version"],
        "sourceKind": package.source_kind,
        "packageId": package.manifest["package_id"],
        "producerId": package.manifest["producer_id"],
        "datasetId": package.manifest["dataset_id"],
        "revision": package.manifest["revision"],
        "packageDigest": package.package_digest,
        "itemCount": package.item_count,
        "fileCount": package.file_count,
        "totalBytes": package.total_bytes,
        "errors": [],
    }
