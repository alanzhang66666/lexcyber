import hashlib
import io
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile

from domain.documents.repository import load_document, persist_pages, register_document
from skill_runtime.executor import SkillExecutor
from skill_runtime.schemas import SkillRequest

router = APIRouter()
executor = SkillExecutor()


@router.post("/v1/cases/{case_id}/documents")
async def upload_document(case_id: str, file: UploadFile = File(...)):
    data = await file.read()
    sha256 = hashlib.sha256(data).hexdigest()
    storage_key = None
    try:
        from storage.object_storage import put_object

        storage_key = put_object(sha256, io.BytesIO(data), file.content_type or "application/octet-stream")
    except Exception:
        storage_key = None
    import base64

    metadata: dict[str, Any] = {"size": len(data)}
    if storage_key is None and len(data) <= 2_000_000:
        metadata["content_base64"] = base64.b64encode(data).decode("ascii")
    try:
        return register_document(case_id, file.filename or "upload.bin", file.content_type, storage_key, sha256, metadata)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/v1/documents/{document_id}")
def get_document(document_id: str):
    try:
        document = load_document(document_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not document:
        raise HTTPException(status_code=404, detail="document not found")
    metadata = dict(document.get("metadata") or {})
    metadata.pop("content_base64", None)
    document["metadata"] = metadata
    return document


@router.post("/v1/documents/{document_id}/parse")
def parse_document(document_id: str):
    try:
        document = load_document(document_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not document:
        raise HTTPException(status_code=404, detail="document not found")
    filename = (document.get("filename") or "").lower()
    skill_id = "document.parse.docx" if filename.endswith(".docx") else "document.parse.pdf"
    payload = {"document_id": document_id, "filename": document.get("filename"), "content_base64": (document.get("metadata") or {}).get("content_base64")}
    if not payload["content_base64"]:
        payload["text"] = ""
    result = executor.execute(SkillRequest(skill_id=skill_id, input=payload))
    pages = (result.output or {}).get("pages") or []
    try:
        persist_pages(document_id, pages)
    except Exception:
        pass
    return result


@router.get("/v1/documents/{document_id}/content")
def document_content(document_id: str):
    document = get_document(document_id)
    return {"document_id": document_id, "pages": document.get("pages") or [], "text": "\n".join(page.get("text", "") for page in document.get("pages") or [])}
