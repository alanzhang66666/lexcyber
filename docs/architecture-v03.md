# LexCyber 0.8 公共架构基线

产品现状与图：[中文 0.8](lexcyber-0.8.zh-CN.md) · [English 0.8](lexcyber-0.8.en.md)。本文件只写边界，不写部署承诺。三套入口可以独立开发、测试和发布，浏览器只访问 Nginx 暴露的公共入口。

```text
Browser -> Nginx :18080 -> web static assets
                         -> /v1/* -> Java application -> PostgreSQL app schema
                                                   -> MinIO object storage
                                                   -> internal HTTP + service token
                                                   -> Python engine -> Redis/Dramatiq
                                                                    -> PostgreSQL engine schema
                                                                    -> ModelGateway -> external model API
```

## What is on main (T1)

This is not a stub-only cut. **T1 public APIs are on `main`**, measured against [`contracts/public-api.yaml`](../contracts/public-api.yaml). Request and response samples are in [`LexCyber_T1接口交接样例.md`](../LexCyber_T1接口交接样例.md). The status table is the [README T1 section](../README.md#t1-on-main).

| Area | On `main` |
| --- | --- |
| Cases / documents | Bearer + owner scope. Upload stores bytes in MinIO, then creates a `document.parse` task (`parseTaskId`). PDF/DOCX only. |
| Auto-parse | Engine re-reads stored bytes and returns `workflow.output` with `content.schemaVersion=document.parse.v1`. |
| Facts | `GET`/`PUT /v1/cases/{id}/facts` and `POST .../facts/confirm`. Confirm locks further `PUT` (`409`). |
| Reserved-task auth | `document.parse` and `model.probe` require `Authorization: Bearer`. Unauthenticated create is `401`. |
| Owned `storageKey` | Clients must not send object keys. The server overwrites `storageKey` / `caseId` from the owned document. |
| `model.probe` | Authenticated task; Engine calls ModelGateway. A real provider + key in Compose `.env.v03` is required for a non-stub result. |

Caseless stub tasks stay public so the developer console can still submit a generic workflow without a session. That path does not replace the T1 case/document APIs.

**Still `501` (T3 not wired):** `POST /v1/sources/search` returns `SOURCE_SEARCH_UNAVAILABLE`. `metadata.taskType=sentencing.calculate` returns `SENTENCING_UNAVAILABLE` while `SENTENCING_ENABLED=false`. Retrieval signoff remains pending in [`t1-retrieval-boundary.md`](t1-retrieval-boundary.md). T2 case-center list/create/workspace/facts are on `main`. Formal docket/analysis stay disconnected. T3 datasets/rules/index are **not** done.

## Ownership

| Area | Owner | Rule |
| --- | --- | --- |
| `app` schema | Java | Cases, document registration, public tasks, result versions, reviews and business audit. |
| `engine` schema | Python | Execution leases, stage checkpoints, skill execution records and engine audit. |
| Objects | Java boundary | MinIO stores originals and large artifacts; database stores references, hashes and metadata. Engine may re-read owned bytes for `document.parse`. |
| Model access | Python | Only `ModelGateway` may call the configured external model API. |
| Public contract | `contracts/public-api.yaml` | Java owns stable public DTOs; `AgentState` is never exposed. |

## State and review invariants

```text
queued -> running -> completed
                 -> waiting_review -> completed / rejected
                 -> failed
                 -> timed_out
```

- A review is bound to one immutable result version.
- Approval only confirms that version; it never resumes or re-runs a worker.
- Retry creates a new execution and preserves the old result, audit and decision.
- Redis carries execution numbers only. Result and review state are durable in PostgreSQL.
- Internal engine calls require `X-Service-Token`; browsers never call Python, Redis, PostgreSQL or MinIO directly.
- After upload, T2/T3 poll `parseTaskId` and read body text from `/v1/tasks/{id}/result` only. They must not create a second parse task.

## Delivery status

1. Contract, schema ownership and error envelope are frozen.
2. Java application boundary and Flyway migrations are on `main`.
3. Workflow execution sits behind the Python internal API with durable engine records. Default `WORKFLOW_PROFILE=stub` remains; T1 also runs `document.parse` and `model.probe`.
4. Vue case-center list/create/workspace/upload/facts are on `main`. Formal docket and sentencing pages show 未接通 on purpose.
5. The supported local runtime is Compose with real PostgreSQL, Redis and MinIO (`.env.v03`).
