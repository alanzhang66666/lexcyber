# ADR-0001 — ArtifactVersion 发布幂等的权威绑定

> 状态：Accepted。裁决 v1.3 内部矛盾 #1（§8.6 vs §4.6.10 vs §4.6.5）。

## Context

v1.3 对「同一 completed Execution 只能发布一个 ArtifactVersion」有三处不一致表述：

- §8.6 建议 `artifact_version.execution_id UNIQUE`；
- §4.6.10 用独立表 `app.execution_publication` 做绑定；
- §4.6.5 把 `artifact_version.execution_id` 声明为 `NULL` 可空。

三处同时存在时无法判断哪个是权威，也无法回答「手工发布的 ArtifactVersion（无 Execution）是否占用 execution_id 唯一位」。

## Decision

1. `app.execution_publication` 是执行→工件发布的**唯一权威绑定表**，承载 `execution_id`（PK）、`artifact_version_id`、`completion_identity`、`output_hash`。
2. `artifact_version.execution_id` 保留为**冗余读取列**（便于审计查询不经 join），另加部分唯一索引作第二层防线：

   ```sql
   CREATE UNIQUE INDEX ux_artifact_version_execution
     ON app.artifact_version(execution_id) WHERE execution_id IS NOT NULL;
   ```

3. 手工发布路径（无 Execution 的人工/导入写入）使用 `execution_id IS NULL`，不写 `execution_publication`。
4. `execution_publication` 的插入必须与 `artifact_version` 的插入处于**同一 `app` 事务**（INV-DB-DEP-001 同款原子性要求）。

## Consequences

- 同一 completed Execution 重放：先查 `execution_publication`，命中且 `completion_identity + output_hash` 相同 → 直接返回既有 `artifact_version_id`；hash 不同 → 阻断 + 审计异常（INV-DB-PUB-002）。
- `Execution.failed` 不产生产物（INV-ARTIFACT-002），因此 `execution_publication` 不会有 failed execution 的行。
- 手工发布与 Engine 发布共用同一张 `artifact_version`，下游读取不需要区分来源。

## Alternatives Considered

- 只靠 `artifact_version.execution_id UNIQUE`：无法回答「相同 execution、不同 hash」的阻断语义，也无法区分「已发布」与「发布过但行被回滚」。
- 只靠 `execution_publication` 不加部分唯一索引：放弃了一道数据库层防线，且审计查询要多一次 join。

## Migration / Compatibility Notes

- 手工发布路径被 `/v1` 模块 PUT 适配层与 `scripts/import_three_case_demo.py` 依赖。
- `artifact_version.execution_id` 不建跨 schema 外键（v1.3 §4.6.1 原则 3：不跨 ownership 建业务 FK）。
