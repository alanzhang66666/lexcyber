# LexCyber 0.8 product note

[中文](lexcyber-0.8.zh-CN.md) · [README](../README.md)

**Version:** 0.8
**Role:** An auditable task-execution and case-document workbench. It assists review. It does not replace judicial discretion and does not issue sentencing, liability, or crime conclusions.

Open `http://127.0.0.1:18080`. Health check: `GET /healthz` should report `version: 0.8.0` after Java / Engine images are rebuilt.

---

## 1. Main system architecture

Mapped to [`docker-compose.yml`](../docker-compose.yml) and [`nginx/nginx.v03.conf`](../nginx/nginx.v03.conf). Project name `lexcyber-v03`, env file `.env.v03`. The host exposes only `127.0.0.1:18080`. The browser never calls `java:8080`, `engine:8100`, Postgres, Redis, or MinIO.

### 1.1 Deployment and edge

```mermaid
flowchart TB
  Host["host_127.0.0.1:18080"]
  subgraph compose [Compose_lexcyber-v03]
    Nginx["nginx:8080"]
    Web["web:80_Vue_static"]
    Java["java:8080_Spring_21"]
    EngineApi["engine:8100_uvicorn"]
    Worker["engine-worker_dramatiq"]
    Migrate["engine-migrate_Flyway"]
    Pg[("postgres:5432_lexcyber")]
    Redis[("redis:6379")]
    Minio[("minio:9000_bucket_lexcyber")]
  end
  DeepSeek["external_OpenAI_compatible"]

  Host --> Nginx
  Nginx -->|"GET /healthz"| Java
  Nginx -->|"/v1/*"| Java
  Nginx -->|"/ static"| Web
  Java --> Pg
  Java --> Minio
  Java -->|"ENGINE_BASE_URL + X-Service-Token"| EngineApi
  EngineApi --> Worker
  Worker --> Redis
  Worker --> Pg
  Worker --> Minio
  Worker --> DeepSeek
  Migrate --> Pg
  Java -->|"APP_CALLBACK_BASE_URL"| Java
```

| Service | Image / entry | Role |
| --- | --- | --- |
| `nginx` | `nginx.v03.conf` | `/healthz` and `/v1/` → Java; everything else → `web:80`; 50m upload cap |
| `web` | Vue build | Login, case center, workspace, tasks/reviews |
| `java` | Spring Boot 21, Flyway `app` | Public API, ownership, MinIO writes, Engine dispatch |
| `engine` | `uvicorn engine.run_api_v03:app` | Internal execution API |
| `engine-worker` | `dramatiq engine.run_api_v03` | Queue consumer, parse, probe |
| `engine-migrate` | Flyway → schema `engine` | One-shot migrate |
| `postgres` | DB `lexcyber` | `app` (`lex_app`) and `engine` (`lex_engine`) split users |
| `redis` | AOF | Execution numbers only; no result bodies |
| `minio` | bucket `lexcyber` | Originals; DB stores key / hash / metadata |

### 1.2 Java application

Root package: `com.lexcyber.server`. Public contract [`contracts/public-api.yaml`](../contracts/public-api.yaml) `0.8.0`.

```mermaid
flowchart LR
  subgraph edge [Nginx]
    V1["/v1"]
    Hz["/healthz"]
  end
  subgraph javaApp [Java]
    Auth["AuthController"]
    Cases["CaseController"]
    Docs["DocumentController"]
    Facts["FactController"]
    Tasks["TaskController"]
    Reviews["ReviewController"]
    Sources["SourceSearchController"]
    Health["HealthController"]
    Disp["EngineDispatcher"]
    Cb["EngineResultCallback"]
    Store["MinioObjectStorage"]
    Fly["Flyway_app"]
  end
  V1 --> Auth
  V1 --> Cases
  V1 --> Docs
  V1 --> Facts
  V1 --> Tasks
  V1 --> Reviews
  V1 --> Sources
  Hz --> Health
  Docs --> Store
  Tasks --> Disp
  Disp -->|"POST /internal/v1"| EngineApi2["engine:8100"]
  EngineApi2 --> Cb
  Auth --> Fly
  Cases --> Fly
  Docs --> Fly
  Facts --> Fly
  Tasks --> Fly
  Reviews --> Fly
  Sources -->|"501 until T3"| EngineApi2
```

| Area | Types | Public paths |
| --- | --- | --- |
| Identity | `AuthController` / `AuthService` | `/v1/auth/register` `login` `logout` `session` |
| Cases | `CaseService` | `/v1/cases` |
| Documents | `DocumentService` | `/v1/cases/{id}/documents`, `/v1/documents/{id}` |
| Facts | `FactService` | `/v1/cases/{id}/facts`, `.../confirm` |
| Tasks | `TaskService` / `TaskPolicies` | `/v1/tasks`, status, `/result`, `/retry` |
| Reviews | `ReviewService` | `/v1/reviews` (Bearer + owned case; see [t1-api-01-increment.md](t1-api-01-increment.md)) |
| Search gate | `SourceSearchController` / `EngineSourceClient` | `POST /v1/sources/search` → 501 today |
| Engine bridge | `EngineDispatcher`, `EngineResultCallbackController` | Internal HTTP + `X-Service-Token` |

`document.parse` and `model.probe` require Bearer. Upload writes MinIO then creates parse and overwrites a client `storageKey`.

### 1.3 Engine internals

Internal contract [`contracts/internal-engine-api.yaml`](../contracts/internal-engine-api.yaml). Default `WORKFLOW_PROFILE=stub`.

```mermaid
flowchart TB
  Java2["Java_Dispatcher"]
  subgraph engineProc [engine_uvicorn]
    Api["engine.api"]
    StoreE["engine.store"]
  end
  subgraph workerProc [engine_worker]
    W["engine.worker"]
    Wf["engine.workflow"]
    Parse["document_parse"]
    Probe["model_probe"]
    Skills["skill_runtime_PDF_DOCX"]
    SrcAd["adapters.sources_501"]
    SenAd["adapters.sentencing_501"]
    Gw["ModelGateway"]
    Obj["object_store_MinIO"]
  end
  Java2 -->|"X-Service-Token"| Api
  Api --> StoreE
  Api --> W
  W --> Wf
  W --> Parse
  W --> Probe
  Parse --> Skills
  Parse --> Obj
  Probe --> Gw
  W --> SrcAd
  W --> SenAd
  StoreE --> Pg2[("schema_engine")]
  W --> Pg2
  W --> Redis2[("Redis_queue")]
  Gw --> Ext["MODEL_API_BASE_URL"]
  W -->|"callback /internal/engine/results"| Java2
```

| Code | Role |
| --- | --- |
| `engine/api.py` | FastAPI 0.8.0, `/healthz`, accept internal tasks |
| `engine/worker.py` + `workflow.py` | Leases, checkpoints, stub / domain tasks |
| `document_parse.py` | Re-read MinIO bytes; emit `document.parse.v1` |
| `model_probe.py` | External model only via `ModelGateway` |
| `adapters/sources.py` | `SOURCE_SEARCH_UNAVAILABLE` |
| `adapters/sentencing.py` | `SENTENCING_UNAVAILABLE` |
| `engine/migrations` | Flyway `engine` schema |
---

## 2. Team tracks and wiring

Mapped to `技术分工0906.md` (local file; do not commit).

```mermaid
flowchart LR
  T2ui[T2_Vue]
  T1java[T1_Java]
  T1eng[T1_Engine]
  Parse[document_parse_done]
  Probe[model_probe_done]
  Search[sources_search_501]
  Sentence[sentencing_501]
  T3data[T3_datasets]
  T3rules[T3_rules]
  T3idx[T3_index]

  T2ui --> T1java
  T1java --> T1eng
  T1eng --> Parse
  T1eng --> Probe
  T1eng --> Search
  T1eng --> Sentence
  T3data -.-> Parse
  T3rules -.-> Sentence
  T3idx -.-> Search
```

| Track | Status in 0.8 |
| --- | --- |
| T1 | **On `main`.** Cases/documents/auto-parse, facts, reserved-task auth, `storageKey` bind, real `model.probe` |
| T2 | **Main path on `main`.** Four-entry nav, list/create/upload/workspace parse/facts. Formal docket/analysis show “not connected” |
| T3 | **Not started.** No `datasets/`; search and sentencing adapters return 501 |

Public contract: [`contracts/public-api.yaml`](../contracts/public-api.yaml) (`info.version: 0.8.0`). Internal: [`contracts/internal-engine-api.yaml`](../contracts/internal-engine-api.yaml).

---

## 3. Case path

Upload creates `document.parse`. T2 only polls `parseTaskId` and reads body text from `/v1/tasks/{id}/result`. Do not create a second parse task. Do not send `storageKey`.

```mermaid
sequenceDiagram
  participant User
  participant Vue
  participant Java
  participant MinIO
  participant Engine

  User->>Vue: sign in
  Vue->>Java: POST /v1/auth/login
  User->>Vue: create case
  Vue->>Java: POST /v1/cases
  User->>Vue: upload PDF or DOCX
  Vue->>Java: POST /v1/cases/{id}/documents
  Java->>MinIO: put object
  Java->>Java: create document.parse
  Java-->>Vue: documentId and parseTaskId
  loop poll
    Vue->>Java: GET /v1/tasks/{parseTaskId}
  end
  Java->>Engine: internal execute
  Engine->>MinIO: read bytes
  Engine-->>Java: document.parse.v1
  Vue->>Java: GET /v1/tasks/{id}/result
```

Task states:

```mermaid
stateDiagram-v2
  [*] --> queued
  queued --> running
  running --> completed
  running --> waiting_review
  running --> failed
  running --> timed_out
  waiting_review --> completed
  waiting_review --> rejected
```

A review is bound to one immutable result version. Approve does not rerun the worker. Retry starts a new execution and keeps the old result.

---

## 4. Local start

```powershell
Copy-Item .env.v03.example .env.v03
docker compose --env-file .env.v03 up --build
curl.exe http://127.0.0.1:18080/healthz
```

Default `WORKFLOW_PROFILE=stub` still accepts a caseless stub task with no session. A real `model.probe` needs `MODEL_*` in `.env.v03`. Credentials stay in process env:

```powershell
$env:LEXCYBER_USERNAME = "<local username>"
$env:LEXCYBER_PASSWORD = "<local password>"
python scripts/t1_local_closeout.py
```

Samples: [`LexCyber_T1接口交接样例.md`](../LexCyber_T1接口交接样例.md). Do not commit `.env.v03` or API keys.

---

## 5. Do not

1. Call Engine, MinIO, or a vector store from the browser
2. Serve `retrieval/corpus.py` sample articles as public search hits
3. Treat unconfirmed sentencing ratios as production rules
4. Show placeholder “Lin” excerpts as real parse or sentence output

Retrieval signoff is still pending: [`t1-retrieval-boundary.md`](t1-retrieval-boundary.md).
