# v0.3 三人协作与交接手册

本手册覆盖本地 Compose 启动、无会话 stub 任务，以及 **已在 `main` 上的 T1 公开 API**。不要把它读成「只有 stub」。

T1 范围与状态表见 [README 的 T1 on main](../README.md#t1-on-main)。请求/响应样例见 [`LexCyber_T1接口交接样例.md`](../LexCyber_T1接口交接样例.md)。不要把口令或 API key 写进本文件。

## 第一次启动

1. 复制 `.env.v03.example` 为 `.env.v03`。
2. 执行 `docker compose --env-file .env.v03 up --build`。

如需使用依赖镜像，可在 `.env.v03` 中设置 `PIP_INDEX_URL`、`NPM_REGISTRY` 和 `MAVEN_MIRROR_URL`；未设置时使用各生态的官方源。
3. 等待 `postgres`、`redis`、`engine`、`java` 和 `nginx` 就绪。
4. 在 `http://127.0.0.1:18080` 提交一个普通任务，再提交一个勾选人工复核的任务。这是无会话的 caseless stub 路径，不需要模型 key。

## T1 已在 main 上的公开 API

属主案件链路需要 `Authorization: Bearer`（`POST /v1/auth/login` 或 `POST /v1/auth/register`）。

已在 `main`：

- 案件 / 材料：Bearer + 属主。上传写入 MinIO，并创建 `document.parse`（响应带 `parseTaskId`）。仅 PDF/DOCX。
- 自动解析：Engine 回读已存字节；结果为 `workflow.output`，`content.schemaVersion=document.parse.v1`。
- 事实：`GET`/`PUT /v1/cases/{id}/facts`，`POST .../facts/confirm`。确认后 `PUT` 返回 `409`。
- 预留任务鉴权：`document.parse` 与 `model.probe` 必须带 Bearer；未登录创建返回 `401`。
- 属主 `storageKey`：客户端不要自己传对象键。服务端从属主材料覆盖 `storageKey` / `caseId`。
- `model.probe`：已鉴权任务；Engine 走 ModelGateway。非 stub 结果需要 Compose `.env.v03` 里的真实 provider 与 key。

仍为 `501`（T3 未接线）：`POST /v1/sources/search` → `SOURCE_SEARCH_UNAVAILABLE`；`metadata.taskType=sentencing.calculate` → `SENTENCING_UNAVAILABLE`。检索会签仍见 [`t1-retrieval-boundary.md`](t1-retrieval-boundary.md)（pending）。T2 案件中心页、T3 数据集 / 规则 / 索引 **未做**。

上传成功后只轮询 `parseTaskId`，正文只从 `GET /v1/tasks/{id}/result` 读。不要再 `POST /v1/tasks` 建解析任务，也不要从浏览器打 Engine 或 MinIO。

本地复验用环境变量里的账号，不要把口令写进脚本或文档：

```powershell
$env:LEXCYBER_USERNAME = "<local username>"
$env:LEXCYBER_PASSWORD = "<local password>"
python scripts/t1_local_closeout.py
```

## 一次任务的生命周期

无会话 stub（开发控制台仍走这条）：

```text
POST /v1/tasks
  -> app.tasks + app.task_dispatch_outbox
  -> Java Dispatcher
  -> Engine idempotent execution + Redis
  -> StubWorkflowRunner
  -> engine.executions terminal state
  -> Java callback / reconciliation poll
  -> app.result_versions (+ app.review_records when needed)
  -> GET /v1/tasks/{id}
```

T1 属主解析（上传即建任务）：

```text
POST /v1/auth/login
  -> POST /v1/cases
  -> POST /v1/cases/{id}/documents  (MinIO + parseTaskId)
  -> Engine document.parse (re-read stored bytes)
  -> GET /v1/tasks/{parseTaskId}
  -> GET /v1/tasks/{parseTaskId}/result
```

Java 只能写 `app` schema，Engine 只能写 `engine` schema。跨服务数据必须通过内部合约传递，不能直接读取对方表。

状态机固定为 `queued -> running -> completed | waiting_review | failed | timed_out`；
复核决定把 `waiting_review` 推进到 `completed` 或 `rejected`。只有当前
`execution_id` 可以更新任务状态，旧执行的结果只会被记录为历史或返回冲突。

## 协作规则

- 每个功能由一名成员牵头，另外两人从不同服务边界做评审；下一功能轮换牵头人。
- 阶段一由主设计牵头确认合约、状态机和数据库边界；阶段二由成员 A 牵头任务主链、成员 B 负责故障场景；阶段三由成员 B 牵头复核/审计、成员 A 联调接口和界面；阶段四三人共同收口 Compose、CI、文档和交接演练。
- 合约、Flyway 迁移、状态机和身份校验必须由主设计最终确认。
- 提交说明写明影响的服务、数据库迁移、失败路径和验证命令。
- 新业务能力应以独立 Skill pack 或 workflow profile 加入，不修改 Stub 的通用语义。T1 预留任务（`document.parse`、`model.probe`）按公开合约走，不把检索或量刑假装已接通。

## 三个交接练习

1. 为任务增加一个公共 metadata 字段，并验证 Java outbox、Engine payload、结果审计均能看到它。
2. 新增一个不含业务规则的 core Skill，并为成功、拒绝和超时分别增加测试。
3. 为复核记录增加一个状态展示字段，完成 Java DTO、数据库迁移、前端显示和回调兼容。

属主案件 / 上传 / 解析的对接以 [`LexCyber_T1接口交接样例.md`](../LexCyber_T1接口交接样例.md) 为准，不要另造第二套解析入口。

## 常见问题

- 任务长时间排队：检查 `app.task_dispatch_outbox.last_error` 和 Engine service token。
- 任务执行完成但 API 未更新：检查 Java callback 日志，随后确认 reconciliation poller 是否运行。
- 复核操作返回 503：确认当前环境的 `REVIEW_AUTH_MODE`；生产默认关闭，开发 Compose 使用代理注入的 `local-reviewer`。
- Legal Skill 未出现：这是默认行为；设置 `WORKFLOW_PROFILE=legal` 仅用于显式扩展测试。
- 案件 / 上传 / 预留任务返回 401：需要 Bearer；caseless stub 任务仍可无会话创建。
- `sources/search` 或 `sentencing.calculate` 返回 501：预期。T3 未接线，不要改 adapter 绕过会签。
