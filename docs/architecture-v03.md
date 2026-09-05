# LexCyber v0.3 公共架构基线

本文件是三语言重构的边界说明，不是部署承诺。三套入口可以独立开发、测试和发布，浏览器只访问 Nginx 暴露的公共入口。

```text
Browser -> Nginx :18080 -> web static assets
                         -> /v1/* -> Java application -> PostgreSQL app schema
                                                   -> MinIO object storage
                                                   -> internal HTTP + service token
                                                   -> Python engine -> Redis/Dramatiq
                                                                    -> PostgreSQL engine schema
                                                                    -> ModelGateway -> external model API
```

## Ownership

| Area | Owner | Rule |
| --- | --- | --- |
| `app` schema | Java | Cases, document registration, public tasks, result versions, reviews and business audit. |
| `engine` schema | Python | Execution leases, stage checkpoints, skill execution records and engine audit. |
| Objects | Java boundary | MinIO stores originals and large artifacts; database stores references, hashes and metadata. |
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

## Delivery order

1. Freeze this contract, schema ownership and error envelope.
2. Add Java application boundary and Flyway migrations.
3. Move workflow execution behind the Python internal API and durable engine records.
4. Add the Vue/Vite typed client skeleton; page-level product features follow after the chain is proven.
5. Run the full Compose chain with real PostgreSQL, Redis and MinIO before integration acceptance.
