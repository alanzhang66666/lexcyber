# v0.3 三人协作与交接手册

## 第一次启动

1. 复制 `.env.v03.example` 为 `.env.v03`。
2. 执行 `docker compose --env-file .env.v03 up --build`。

如需使用依赖镜像，可在 `.env.v03` 中设置 `PIP_INDEX_URL`、`NPM_REGISTRY` 和 `MAVEN_MIRROR_URL`；未设置时使用各生态的官方源。
3. 等待 `postgres`、`redis`、`engine`、`java` 和 `nginx` 就绪。
4. 在 `http://127.0.0.1:18080` 提交一个普通任务，再提交一个勾选人工复核的任务。

## 一次任务的生命周期

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

Java 只能写 `app` schema，Engine 只能写 `engine` schema。跨服务数据必须通过内部合约传递，不能直接读取对方表。

状态机固定为 `queued -> running -> completed | waiting_review | failed | timed_out`；
复核决定把 `waiting_review` 推进到 `completed` 或 `rejected`。只有当前
`execution_id` 可以更新任务状态，旧执行的结果只会被记录为历史或返回冲突。

## 协作规则

- 每个功能由一名成员牵头，另外两人从不同服务边界做评审；下一功能轮换牵头人。
- 阶段一由主设计牵头确认合约、状态机和数据库边界；阶段二由成员 A 牵头任务主链、成员 B 负责故障场景；阶段三由成员 B 牵头复核/审计、成员 A 联调接口和界面；阶段四三人共同收口 Compose、CI、文档和交接演练。
- 合约、Flyway 迁移、状态机和身份校验必须由主设计最终确认。
- 提交说明写明影响的服务、数据库迁移、失败路径和验证命令。
- 新业务能力应以独立 Skill pack 或 workflow profile 加入，不修改 Stub 的通用语义。

## 三个交接练习

1. 为任务增加一个公共 metadata 字段，并验证 Java outbox、Engine payload、结果审计均能看到它。
2. 新增一个不含业务规则的 core Skill，并为成功、拒绝和超时分别增加测试。
3. 为复核记录增加一个状态展示字段，完成 Java DTO、数据库迁移、前端显示和回调兼容。

## 常见问题

- 任务长时间排队：检查 `app.task_dispatch_outbox.last_error` 和 Engine service token。
- 任务执行完成但 API 未更新：检查 Java callback 日志，随后确认 reconciliation poller 是否运行。
- 复核操作返回 503：确认当前环境的 `REVIEW_AUTH_MODE`；生产默认关闭，开发 Compose 使用代理注入的 `local-reviewer`。
- Legal Skill 未出现：这是默认行为；设置 `WORKFLOW_PROFILE=legal` 仅用于显式扩展测试。
