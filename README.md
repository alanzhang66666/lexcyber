# LexCyber v0.3

LexCyber is a general-purpose, auditable task-execution platform. It provides a stable Java public API, a Python execution Engine, durable PostgreSQL state, Redis work queues, a neutral Stub workflow, and a small Vue developer console. It intentionally does not make sentencing, liability, crime, or other legal conclusions.

## Start the complete local demo

```powershell
Copy-Item .env.v03.example .env.v03
docker compose --env-file .env.v03 up --build
```

Open `http://127.0.0.1:18080`. The console submits a task, polls its state, displays the result reference, and can approve or reject a development review. The default `WORKFLOW_PROFILE=stub` needs no external model key.

```powershell
curl.exe http://127.0.0.1:18080/healthz
./scripts/ready-check.ps1
curl.exe -X POST http://127.0.0.1:18080/v1/tasks `
  -H 'Content-Type: application/json' `
  -d '{"query":"Summarize this generic workflow input","metadata":{"source":"demo"}}'
```

Use `GET /v1/tasks/{id}` for lifecycle and `GET /v1/tasks/{id}/result` for the
immutable Stub content. Review tasks appear at `GET /v1/reviews?status=pending`.

## Service boundaries

```text
Browser -> Nginx -> Java public API -> app schema / result & review ownership
                                  -> Engine internal API (service token)
                              Python Engine -> Redis/Dramatiq -> engine schema
                              Python Engine -> optional model/retrieval adapters
```

The Java service owns the public contract, task lifecycle, result versions, reviews, and business audit. The Engine owns execution leases, checkpoints, Skill execution records, and Engine audit. Internal requests are defined in `contracts/internal-engine-api.yaml`; public requests are defined in `contracts/public-api.yaml`.

The previous v0.2 Compose stack is archived at `legacy/docker-compose.v02.yml` and is not part of the supported runtime.

The console types in `web/src/api-types.ts` are the checked-in snapshot of the
public contract. Update that snapshot in the same change as an OpenAPI edit.

## Development conventions

- Keep the default workflow and UI generic; add domain behavior as an explicit Skill pack or workflow profile.
- Existing Legal Skills remain in the repository as an optional `legal` extension and are not used by the default v0.3 Stub path.
- Database changes are forward-only Flyway migrations. Do not edit released migrations.
- Every asynchronous boundary must be idempotent, observable, and covered by a failure-path test.
- Changes are reviewed vertically by all three engineers: the change driver and two cross-service reviewers.

## Checks

```powershell
python -m ruff check .
python -m pytest -q
npm --prefix web run build
```

The CI pipeline additionally compiles Java 21, validates both OpenAPI contracts, and runs a v0.3 Compose smoke test.
