import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from engine.import_package import (
    CANONICALIZATION_VERSION,
    MAX_COMPRESSION_RATIO,
    MAX_PACKAGE_ENTRIES,
    PACKAGE_SCHEMA_VERSION,
    calculate_package_digest,
    load_import_package,
    validate_import_package,
)


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _write_package(root: Path, item_count: int) -> Path:
    items = []
    for index in range(item_count):
        item_id = f"item-{index + 1}"
        case_id = f"external-case-{index + 1}"
        document_id = f"doc-{index + 1}"
        material = f"%PDF-1.4\n% fixture {index + 1}\n%%EOF\n".encode()
        material_hash = _sha256(material)
        bundle = {
            "schema_version": "lexcyber.case-bundle.v1",
            "case_id": case_id,
            "case_code": f"CASE-{index + 1}",
            "title": f"Fixture {index + 1}",
            "jurisdiction": "CN",
            "analysis_as_of_date": "2026-09-18",
            "documents": [
                {
                    "id": document_id,
                    "role": "case_material",
                    "title": "material.pdf",
                    "archive_entry": "material.pdf",
                    "sha256": material_hash,
                    "source_version": f"sha256:{material_hash[:16]}",
                }
            ],
            "actors": [{"id": f"actor-{index + 1}", "type": "person", "name": "测试主体", "role": "subject"}],
            "evidence": [
                {
                    "id": f"evidence-{index + 1}",
                    "type": "source",
                    "label": "测试证据",
                    "document_id": document_id,
                    "locator": {"page": 1},
                }
            ],
            "facts": [],
            "events": [],
            "analyses": {"compliance": {}, "conviction": {}},
        }
        payload = _json_bytes(bundle)
        item_root = root / "items" / item_id
        item_root.mkdir(parents=True)
        (item_root / "case.json").write_bytes(payload)
        (item_root / "material.pdf").write_bytes(material)
        items.append(
            {
                "item_id": item_id,
                "external_case_id": case_id,
                "resource_type": "case",
                "payload": {
                    "path": f"items/{item_id}/case.json",
                    "media_type": "application/vnd.lexcyber.case-bundle+json;version=1",
                    "schema_version": "lexcyber.case-bundle.v1",
                    "size": len(payload),
                    "sha256": _sha256(payload),
                },
                "files": [
                    {
                        "file_id": f"file-{index + 1}",
                        "document_id": document_id,
                        "role": "case_material",
                        "path": f"items/{item_id}/material.pdf",
                        "media_type": "application/pdf",
                        "size": len(material),
                        "sha256": material_hash,
                    }
                ],
            }
        )
    manifest = {
        "schema_version": PACKAGE_SCHEMA_VERSION,
        "package_id": "fixture-package",
        "producer_id": "fixture-producer",
        "dataset_id": "fixture-dataset",
        "revision": "1",
        "created_at": "2026-09-18T08:00:00Z",
        "items": items,
        "package_digest": {
            "algorithm": "sha256",
            "canonicalization": CANONICALIZATION_VERSION,
            "value": "0" * 64,
        },
    }
    manifest["package_digest"]["value"] = calculate_package_digest(manifest)
    (root / "case-import.json").write_bytes(_json_bytes(manifest))
    return root


def _mark_first_zip_entry_encrypted(archive_path: Path) -> None:
    data = bytearray(archive_path.read_bytes())
    for signature, flag_offset in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
        header_offset = data.index(signature)
        flags_start = header_offset + flag_offset
        flags = int.from_bytes(data[flags_start : flags_start + 2], "little")
        data[flags_start : flags_start + 2] = (flags | 0x1).to_bytes(2, "little")
    archive_path.write_bytes(data)


@pytest.mark.parametrize("item_count", [1, 3])
def test_directory_package_supports_one_or_many_items(tmp_path: Path, item_count: int):
    package = load_import_package(_write_package(tmp_path / "package", item_count))
    assert package.source_kind == "directory"
    assert package.item_count == item_count
    assert package.file_count == item_count
    assert len(package.payloads) == item_count


def test_zip_and_directory_have_the_same_package_digest(tmp_path: Path):
    root = _write_package(tmp_path / "package", 2)
    directory = load_import_package(root)
    archive_path = tmp_path / "package.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(root).as_posix())
    zipped = load_import_package(archive_path)
    assert zipped.source_kind == "zip"
    assert zipped.package_digest == directory.package_digest
    assert zipped.item_count == directory.item_count


def test_duplicate_document_identity_is_rejected(tmp_path: Path):
    root = _write_package(tmp_path / "package", 1)
    manifest_path = root / "case-import.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    original = manifest["items"][0]["files"][0]
    duplicate_path = root / "items" / "item-1" / "duplicate.pdf"
    duplicate_path.write_bytes((root / original["path"]).read_bytes())
    manifest["items"][0]["files"].append(
        {**original, "file_id": "file-duplicate", "path": "items/item-1/duplicate.pdf"}
    )
    manifest["package_digest"]["value"] = calculate_package_digest(manifest)
    manifest_path.write_bytes(_json_bytes(manifest))

    report = validate_import_package(root)
    assert report["valid"] is False
    assert "DUPLICATE_DOCUMENT_ID" in {item["code"] for item in report["errors"]}


def test_zip_compression_ratio_limit_is_rejected(tmp_path: Path):
    archive_path = tmp_path / "compression-ratio.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("payload.bin", b"0" * (MAX_COMPRESSION_RATIO * 1024))

    report = validate_import_package(archive_path)

    assert report["valid"] is False
    assert any(
        item["code"] == "INVALID_PACKAGE_SOURCE"
        and "ZIP compression ratio exceeds limit" in item["message"]
        for item in report["errors"]
    )


def test_zip_entry_count_limit_is_rejected(tmp_path: Path):
    archive_path = tmp_path / "entry-count.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_STORED) as archive:
        for index in range(MAX_PACKAGE_ENTRIES + 1):
            archive.writestr(f"entries/{index}.bin", b"")

    report = validate_import_package(archive_path)

    assert report["valid"] is False
    assert any(
        item["code"] == "INVALID_PACKAGE_SOURCE"
        and "ZIP exceeds entry or total size limit" in item["message"]
        for item in report["errors"]
    )


def test_encrypted_zip_entry_is_rejected(tmp_path: Path):
    archive_path = tmp_path / "encrypted-entry.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("payload.bin", b"payload")
    _mark_first_zip_entry_encrypted(archive_path)

    report = validate_import_package(archive_path)

    assert report["valid"] is False
    assert any(
        item["code"] == "INVALID_PACKAGE_SOURCE"
        and "encrypted ZIP entries are forbidden" in item["message"]
        for item in report["errors"]
    )
