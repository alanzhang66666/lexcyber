# LexCyber

Product notes with architecture diagrams: [中文 0.8](docs/lexcyber-0.8.zh-CN.md) · [English 0.8](docs/lexcyber-0.8.en.md).

**Target architecture**: `LexCyber-system-architecture-v1.3-postgresql-physical-model.md` (normative). Decisions resolving internal ambiguities: `docs/adr/ADR-0001`–`0006`. Delivery status: `docs/architecture-roadmap.md`.

**契约版本：** 0.8.0
**现状日期：** 2026-09-19

LexCyber is a general-purpose, auditable task-execution platform. It provides a
stable Java public API, a Python execution Engine, durable PostgreSQL state,
Redis work queues, MinIO object storage, a default Stub workflow, and a small
Vue developer console. It intentionally does not make sentencing, liability,
crime, or other legal conclusions.

**LexCyber 0.8.** The supported local runtime is the Compose stack in
`docker-compose.yml` (project name remains `lexcyber-v03`; env file is still
`.env.v03`). **T1 backend contracts are on `main`**: owner-scoped cases and
documents with upload-time auto-parse, facts, reserved-task auth, owned
`storageKey` bind, `model.probe`, opaque drafts, and case-level compliance /
conviction shells. T3 Engine adapters for search and sentencing are on `main`,
but the Compose flags stay off. Public source search, sentencing,
`compliance.analyze`, and `conviction.analyze` therefore remain `501` by
default with codes `SOURCE_SEARCH_UNAVAILABLE`, `SENTENCING_UNAVAILABLE`,
`COMPLIANCE_UNAVAILABLE`, and `CONVICTION_UNAVAILABLE`. Opening only the Java
sentencing flag creates a task that then `failed` on the Engine side.
T2 frontend case-center (list/create/workspace/facts) is on `main`. The formal
module pages are merged into local `main`: docket reads documents +
`document.parse.v1` results, analysis runs `sentencing.calculate` when the
flags are enabled, sources searches the Engine adapter, and review detail can
archive decided records. With `SENTENCING_ENABLED` /
`LEGAL_SOURCE_SEARCH_ENABLED` on and the three-case demo imported, the
case-center → conviction → sentencing → review/archive flow runs end to end.
Compose defaults still keep both flags off.

## Start the complete local demo

```powershell
Copy-Item .env.v03.example .env.v03
docker compose --env-file .env.v03 up --build
```

Open `http://127.0.0.1:18080`. The console submits a generic stub task, polls
its state, displays the result reference, and can approve or reject a
development review. The default `WORKFLOW_PROFILE=stub` needs no external model
key. `.env.v03` is gitignored; put real `MODEL_*` values there only when you
need a live model call.

```powershell
curl.exe http://127.0.0.1:18080/healthz
./scripts/ready-check.ps1
curl.exe -X POST http://127.0.0.1:18080/v1/tasks `
  -H 'Content-Type: application/json' `
  -d '{"query":"Summarize this generic workflow input","metadata":{"source":"demo"}}'
```

Use `GET /v1/tasks/{id}` for lifecycle and `GET /v1/tasks/{id}/result` for the
immutable Stub content. Caseless stub tasks stay public so this path still works
without a session. Reviews require Bearer and are scoped to cases the account
owns (`GET /v1/reviews`); see [`docs/t1-api-01-increment.md`](docs/t1-api-01-increment.md).

## T1 on main

Measured against the public API (`contracts/public-api.yaml`). Request and
response samples for T2/T3 are in [`LexCyber_T1接口交接样例.md`](LexCyber_T1接口交接样例.md).
Three-case field increment and owner-scoped reviews: [`docs/t1-api-01-increment.md`](docs/t1-api-01-increment.md).

| Area | Status on `main` |
| --- | --- |
| Cases / documents | Bearer + owner scope. Upload stores bytes in MinIO, then creates a `document.parse` task (`parseTaskId`). PDF/DOCX only. |
| Auto-parse | Engine re-reads stored bytes and returns `workflow.output` with `content.schemaVersion=document.parse.v1` (locators). Fatal/timeout map to `DOCUMENT_PARSE_FAILED` / `DOCUMENT_PARSE_TIMEOUT`. |
| Facts | `GET`/`PUT /v1/cases/{id}/facts` and `POST .../facts/confirm`. Confirm locks further `PUT` (`409`). Optional item `verificationStatus` / `sourceVersion`; case-level confirm does not rewrite item status. |
| Reviews | Bearer + owner case via task / draft / stored `case_id`. Payload includes `caseId` and derived `module`. Optional `?module=` / `?archiveStatus=`. `POST /v1/cases/{id}/reviews` can open a review without a task. `POST /v1/reviews/{id}/archive`. Other-case / missing → `404`; unauthenticated list is `401`, not the global queue. |
| Drafts | Opaque `GET`/`POST`/`PUT /v1/cases/{id}/drafts`. Body is a string; version mismatch is `409`. Optional `templateVersion` / `sourceVersion`. A successful `PUT` supersedes pending/approved reviews on the old draft version. No Word/PDF and no legal checks. |
| Compliance / conviction shells | Opaque `GET`/`PUT`/`confirm` on `/v1/cases/{id}/compliance` and `/conviction`. Empty GET is `version=0`. Confirmed shells reject further `PUT` (`409 MODULE_CONFIRMED`). `factsStale` is computed; content is not legally validated. |
| Source search | Public `POST /v1/sources/search` stays `501 SOURCE_SEARCH_UNAVAILABLE` while `LEGAL_SOURCE_SEARCH_ENABLED=false`. The T3 adapter is in Engine; the default Compose flag is off. |
| Sentencing | Public create stays `501 SENTENCING_UNAVAILABLE` while Java `SENTENCING_ENABLED=false`. When enabled, unconfirmed facts return `409 FACTS_NOT_CONFIRMED`. Java and Engine flags must both be on; Java-only create becomes a `failed` task. |
| Analyze task types | `compliance.analyze` / `conviction.analyze` stay `501 COMPLIANCE_UNAVAILABLE` / `CONVICTION_UNAVAILABLE`. No Engine dispatch. |
| Reserved-task auth | `document.parse` and `model.probe` require `Authorization: Bearer`. Unauthenticated create is `401`. |
| Owned `storageKey` | Clients must not send object keys. The server overwrites `storageKey` / `caseId` from the owned document; a forged key is ignored. |
| `model.probe` | Authenticated task; Engine calls ModelGateway. A real provider + key in Compose `.env.v03` is required for a non-stub result. |

The Vue case-center list, create, workspace, upload, parse polling, and facts
confirm are wired to these APIs. The formal docket, sentencing-analysis,
source-law, and review pages are also on local `main`: docket reads uploaded
document parse results, while source and sentencing calls preserve the 501
gate when their capability flags are off. No placeholder 林某 excerpts are
used as open-case evidence.

T2/T3 should poll `parseTaskId` after upload and read body text from
`/v1/tasks/{id}/result` only. Do not create a second parse task and do not
call Engine or MinIO from the browser.

## Local closeout and model probe

With Compose already up (`http://127.0.0.1:18080`), use a real local account
via environment variables. Do not hardcode credentials or commit API keys.

```powershell
$env:LEXCYBER_USERNAME = "<local username>"
$env:LEXCYBER_PASSWORD = "<local password>"
python scripts/t1_local_closeout.py
```

`scripts/t1_local_closeout.py` checks reserved-task `401`, public stub tasks,
facts lock, source-search `501`, sentencing `501`, owned `storageKey` bind,
upload auto-parse, and a **real** `model.probe` (Engine must not be on the stub
provider). It expects a local `.t1-smoke-input.docx` (gitignored).

To record a probe independently, load the same `LEXCYBER_*` vars **and** the
real `MODEL_PROVIDER` / `MODEL_API_KEY` from `.env.v03` into the current
shell (`MODEL_PROVIDER` must not be `stub`):

```powershell
./scripts/model-probe.ps1
```

The script writes `docs/model-probe-record.md` and refuses a stub result.

## Service boundaries

```text
Browser -> Nginx -> Java public API -> app schema / result & review ownership
                                  -> Engine internal API (service token)
                              Python Engine -> Redis/Dramatiq -> engine schema
                              Python Engine -> MinIO (parse bytes) / optional model adapters
```

The Java service owns the public contract, task lifecycle, cases, documents,
facts, result versions, reviews, and business audit. The Engine owns execution
leases, checkpoints, Skill execution records, and Engine audit. Internal
requests are defined in `contracts/internal-engine-api.yaml`; public requests
are defined in `contracts/public-api.yaml`.

The v0.2 Python surface was removed (`apps/`, `domain/`, `migrations/`,
`legacy/`, the root `Dockerfile`). The live tree is `web/`, `server/`,
`engine/`, `contracts/`, and `nginx/nginx.v03.conf`. Engine still imports
`models/`, `graph/`, `skill_runtime/`, `skills/`, `retrieval/`, plus the
LangGraph support chain `agents/`, `audit/`, `config/`, `prompts/`,
`storage/`, `tools/` — do not delete those to “clean up.” Use
`.env.v03.example` as the env template.

The console types in `web/src/api-types.ts` are the checked-in snapshot of the
public contract. Update that snapshot in the same change as an OpenAPI edit.

## Development conventions

- Keep the default workflow and UI generic; add domain behavior as an explicit Skill pack or workflow profile.
- Existing Legal Skills remain in the repository as an optional `legal` extension and are not used by the default Stub path.
- Database changes are forward-only Flyway migrations. Do not edit released migrations.
- Every asynchronous boundary must be idempotent, observable, and covered by a failure-path test.
- Changes are reviewed vertically by all three engineers: the change driver and two cross-service reviewers.

## Checks

```powershell
python -m ruff check .
python -m pytest -q
npm --prefix web run build
```

The checked-in CI workflow additionally compiles Java 21, validates both
OpenAPI contracts, and runs a Compose smoke test.
