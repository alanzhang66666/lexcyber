# LexCyber

Product notes with architecture diagrams: [中文 0.8](docs/lexcyber-0.8.zh-CN.md) · [English 0.8](docs/lexcyber-0.8.en.md).

**Target architecture**: `LexCyber-system-architecture-v1.3-postgresql-physical-model.md` (normative). Decisions resolving internal ambiguities: `docs/adr/ADR-0001`–`0006`. Delivery status: `docs/architecture-roadmap.md`.

**契约版本：** 0.8.0（/v1 兼容）+ /v2 生命周期契约
**现状日期：** 2026-09-26

LexCyber is a general-purpose, auditable task-execution platform. It provides a
stable Java public API, a Python execution Engine, durable PostgreSQL state,
Redis work queues, MinIO object storage, a default Stub workflow, and a small
Vue developer console. It intentionally does not make sentencing, liability,
crime, or other legal conclusions.

**LexCyber v1.3 lifecycle (verified end to end on 2026-09-24/26).** The Compose
stack in `docker-compose.yml` runs the full pipeline: versioned facts with CAS
confirmation → module dispatch behind the rule-registry capability gate →
Engine execution consuming approved rule/template packages → idempotent
artifact publication with dependency snapshots → human review → staleness
propagation → archive. Module results only exist via execution+publication;
the legacy `/v1` module write endpoints return `410 MODULE_WRITE_RETIRED`
unless `DEMO_IMPORT_ENABLED=true` (three-case demo import). The
`/v2` contract lives in `contracts/public-api-v2.yaml`; `/v1` remains as the
compat read layer (documents, task polling, review queue, manual drafts,
auth). Engine-side v2 executors — `module_analysis` (compliance / conviction /
distinction), `sentencing_v2`, `document_render` — consume only approved
registry entries and always mark `human_review_required`. Current corpus
sign-offs use the placeholder `e2e-reviewer` and still need real legal-owner
sign-off.

## Start the complete local demo

```powershell
Copy-Item .env.v03.example .env.v03
docker compose --env-file .env.v03 up --build
```

Open `http://127.0.0.1:18080` and register or log in before using the console.
After signing in, open `/tasks` to submit a generic stub task and poll its
state. The result reference identifies the stored result; reviews require a
session and an owned case. The curl example below accepts a caseless generic
stub task without login. The default `WORKFLOW_PROFILE=stub` needs no external model
key. `.env.v03` is gitignored. For a live model call, replace the stub settings
with your provider's `MODEL_PROVIDER`, `MODEL_NAME`, `MODEL_API_BASE_URL` and
`MODEL_API_KEY`. For an OpenAI-compatible endpoint, use `MODEL_PROVIDER=openai`.
The model-probe and local-closeout commands below require these real settings;
they are separate from the offline demo.

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
owns (`GET /v1/reviews`); see [`docs/archive/t1-api-01-increment.md`](docs/archive/t1-api-01-increment.md).

For legal module execution, fill the analysis date when creating the case.
For an existing undated case, set it in the case workspace before dispatching.
Executions bind this date, and retries retain it. Changing the date preserves
historical versions and invalidates confirmed modules and approved drafts;
run and review new results under the new date. Source searches also require
an explicit analysis date. Missing dates never default to today.

## T1 on main

Measured against the public API (`contracts/public-api.yaml`). Request and
response samples for T2/T3 are in [`docs/archive/LexCyber_T1接口交接样例.md`](docs/archive/LexCyber_T1接口交接样例.md).
Three-case field increment and owner-scoped reviews: [`docs/archive/t1-api-01-increment.md`](docs/archive/t1-api-01-increment.md).

| Area | Status on `main` |
| --- | --- |
| Cases / documents | Bearer + owner scope. Upload stores bytes in MinIO, then creates a `document.parse` task (`parseTaskId`). PDF/DOCX only. |
| Auto-parse | Engine re-reads stored bytes and returns `workflow.output` with `content.schemaVersion=document.parse.v1` (locators). Fatal/timeout map to `DOCUMENT_PARSE_FAILED` / `DOCUMENT_PARSE_TIMEOUT`. |
| Facts | `GET`/`PUT /v1/cases/{id}/facts` and `POST .../facts/confirm`. Confirm locks further `PUT` (`409`). Optional item `verificationStatus` / `sourceVersion`; case-level confirm does not rewrite item status. |
| Reviews | Bearer + owner case via task / draft / stored `case_id`. Payload includes `caseId` and derived `module`. Optional `?module=` / `?archiveStatus=`. `POST /v1/cases/{id}/reviews` can open a review without a task. `POST /v1/reviews/{id}/archive`. Other-case / missing → `404`; unauthenticated list is `401`, not the global queue. |
| Drafts | Opaque `GET`/`POST`/`PUT /v1/cases/{id}/drafts`. Body is a string; version mismatch is `409`. Optional `templateVersion` / `sourceVersion`; `artifactVersionId` identifies the immutable body. A successful `PUT` supersedes pending/approved reviews on the old draft version. Download Word auxiliary drafts through `GET /v2/cases/{caseId}/artifact-versions/{artifactVersionId}/export.docx` with Bearer and case ownership; blocked, empty or unresolved bodies return `409`. The server renders real DOCX and verifies its MinIO round trip. Historical downloads preserve their exact version and do not imply current approval. No PDF or substantive legal validation. |
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

The script writes `docs/archive/model-probe-record.md` and refuses a stub result.

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
