# LexCyber

Product notes with architecture diagrams: [中文 0.8](docs/lexcyber-0.8.zh-CN.md) · [English 0.8](docs/lexcyber-0.8.en.md).

LexCyber is a general-purpose, auditable task-execution platform. It provides a
stable Java public API, a Python execution Engine, durable PostgreSQL state,
Redis work queues, MinIO object storage, a default Stub workflow, and a small
Vue developer console. It intentionally does not make sentencing, liability,
crime, or other legal conclusions.

**LexCyber 0.8.** The supported local runtime is the Compose stack in
`docker-compose.yml` (project name remains `lexcyber-v03`; env file is still
`.env.v03`). **T1 backend contracts are on `main`**: owner-scoped cases and
documents with upload-time auto-parse, facts, reserved-task auth, owned
`storageKey` bind, and `model.probe`. Source search and sentencing stay gated
at `501`. T2 frontend case-center (list/create/workspace/facts) is on `main`;
formal docket/analysis pages stay empty until those APIs exist. T3 retrieval
is **not** done.

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
| Facts | `GET`/`PUT /v1/cases/{id}/facts` and `POST .../facts/confirm`. Confirm locks further `PUT` (`409`). |
| Reviews | Bearer + owner case via `tasks.case_id`. Payload includes `caseId`. Other-case / missing → `404`; unauthenticated list is `401`, not the global queue. |
| Source search | `POST /v1/sources/search` returns `501 SOURCE_SEARCH_UNAVAILABLE`. Adapter is not wired; T3 retrieval is not done. |
| Sentencing | `metadata.taskType=sentencing.calculate` returns `501 SENTENCING_UNAVAILABLE` while `SENTENCING_ENABLED=false`. |
| Reserved-task auth | `document.parse` and `model.probe` require `Authorization: Bearer`. Unauthenticated create is `401`. |
| Owned `storageKey` | Clients must not send object keys. The server overwrites `storageKey` / `caseId` from the owned document; a forged key is ignored. |
| `model.probe` | Authenticated task; Engine calls ModelGateway. A real provider + key in Compose `.env.v03` is required for a non-stub result. |

The Vue case-center list, create, workspace, upload, parse polling, and facts
confirm are wired to these APIs. Docket and analysis do not render placeholder
林某 excerpts as the open case; they show 未接通 until formal T2 extraction
and sentencing are connected.

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

The previous v0.2 Compose stack is archived at `legacy/docker-compose.v02.yml`
and is not part of the supported runtime. Do not treat `apps/` as the public
API: that is the pre-0.8 Python surface. Compose does not run it. The live tree
is `web/`, `server/`, `engine/`, `contracts/`, and `nginx/nginx.v03.conf`.
Engine still imports `models/`, `graph/`, `skill_runtime/`, `skills/`, and
`retrieval/` — do not delete those to “clean up.” Use `.env.v03.example`, not
the leftover `.env.example`.

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
