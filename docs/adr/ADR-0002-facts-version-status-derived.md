# ADR-0002 — FactsVersion 不存 status 列，DTO 派生

> 状态：Accepted。裁决 v1.3 内部矛盾 #2（§4.6.2 vs §3.1 / 附录 A.3）。

## Context

v1.3 §4.6.2 明确物理层不保存 `status` 列——`confirmed_at IS NULL` 即 draft，「是否当前 confirmed」由 `facts_head.confirmed_facts_version_id` 唯一决定，「superseded」是读取模型语义不回写。但 §3.1 与附录 A.3 的 `FactsVersion` 对象定义仍列出 `status` 字段。

若物理层与对象模型都存 status，会引入第二事实源：字段值可能与 `confirmed_at`/`facts_head` 指针不一致，违反 INV-DB-SOURCE-001。

## Decision

1. `app.facts_version` 物理表**不建** `status` 列。
2. API/DTO 层的 `FactsVersion.status` 为**只读派生字段**，取值规则：
   - `confirmed_at IS NULL` → `draft`
   - `facts_version_id = facts_head.confirmed_facts_version_id` → `confirmed`
   - `confirmed_at IS NOT NULL` 且不等于 head → `superseded`
3. 契约中该字段标注为 derived/read-only，禁止客户端写入。

## Consequences

- 把旧版本从 confirmed 改为 superseded **不需要 UPDATE** 任何历史行——由 head 指针移动即表达。这是「immutable version」语义能在物理层成立的关键。
- 任何试图「把 status 写回 facts_version 行」的代码都是违规。

## Alternatives Considered

- 物理层冗余存 status + 触发器同步：引入可变性与同步失败面，违背 §4.6.2 设计意图。
- DTO 不暴露 status：前端需要展示「草稿/已确认/已废弃」态，派生字段是最低成本。

## Migration / Compatibility Notes

- 现有 `app.case_facts.status` 在 V14 迁移中只用于一次性回填 `confirmed_at`，随后该表退役。
- `superseded` 语义对 FactsVersion 仅表示「曾 confirmed 但已不是当前基线」，与 Review 的 `superseded` 状态无关。
