# ADR-0003 — 金额 kind 为封闭 CHECK 集合

> 状态：Accepted。裁决 v1.3 内部矛盾 #3（§2.4 只列 6 类，未声明是否封闭）。

## Context

v1.3 §2.4 表格列出 6 个金额 `kind`，但未声明该集合是否封闭。若开放，需要在字典表与未知值处理规则上做额外设计；若封闭，可用 CHECK 约束直接落库。

对既有案件数据的实际口径核查（demo_cases/three_case_demo）确认需要的类别恰为 6 类：

- `payment_settlement_amount`（支付结算金额，帮信「情节严重」要件）
- `illegal_gain`（违法所得）
- `crime_amount`（上游犯罪金额 / 被害人损失）
- `business_revenue`（经营性收入，不入罪量评价）
- `recovery`（追缴数额）
- `fine`（罚金）

## Decision

1. `app.case_amount.kind` 落 `CHECK (kind IN (...))` 封闭集，恰好含上列 6 类。
2. 新增 kind 的唯一路径是：法学会签确认口径 → ADR → 前向 Flyway 迁移扩展 CHECK。**不得**通过应用层绕过 CHECK 写入新 kind。
3. `component_of` 表达组成关系；存在 `component_of` 的金额不得与上游金额重复相加（INV-DATA-001）。

## Consequences

- 未知 kind 在写入时被数据库拒绝，不产生「部分写入」。
- 前端按 6 类渲染，见未知值应显示原文并标记「未识别口径」，不得归入任一类。

## Alternatives Considered

- `amount_kind` 字典表：允许运营期加类，但新增 kind 的法学会签与代码评审本质上仍是变更流程，字典表反而让「加 kind」看起来是配置而非架构变更，风险更高。
- 不约束 kind：违反 INV-DATA-001「不可互换」的实现前提。

## Migration / Compatibility Notes

- `kind` 列类型 `varchar(64)` + CHECK，不使用 PostgreSQL ENUM（§4.6.1 原则 6：ENUM 在前向唯一 Flyway 下演进成本高）。
- 现有模块 content JSONB 里的金额在阶段 2a 抽取时映射到这 6 类；无法映射的一律标 `verification_status = 'conflicted'` 并进入 missing_items，不得强行归类。
