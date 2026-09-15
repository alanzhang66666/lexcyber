"""Small dependency-free guard for the checked-in console type snapshot."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
contract = (ROOT / "contracts" / "public-api.yaml").read_text(encoding="utf-8")
snapshot = (ROOT / "web" / "src" / "api-types.ts").read_text(encoding="utf-8")

required_contract_markers = (
    "/tasks/{taskId}/result:",
    "/auth/login:",
    "/cases:",
    "/documents/{documentId}:",
    "/cases/{caseId}/facts:",
    "/sources/search:",
    "model.probe",
    "sentencing.calculate",
    "SOURCE_SEARCH_UNAVAILABLE",
    "resultVersion:",
    "waiting_review",
    "contentHash:",
    "SessionView:",
    "asOfDate:",
    "parseTaskId:",
    "Idempotency-Key",
)
required_snapshot_markers = (
    "export type TaskStatus",
    "export type TaskType",
    "export type ResultRef",
    "export type ReviewRecord",
    "export type ResultPayload",
    "export type SessionView",
    "export type CaseView",
    "export type DocumentView",
    "export type FactView",
    "export type SourceSearchRequest",
    "waiting_review",
    "asOfDate",
    "parseTaskId",
    "model.probe",
)

missing = [marker for marker in required_contract_markers if marker not in contract]
missing.extend(marker for marker in required_snapshot_markers if marker not in snapshot)
if missing:
    raise SystemExit(f"OpenAPI/type snapshot drift detected: {', '.join(missing)}")

print("OpenAPI contract and console type snapshot markers are aligned")
