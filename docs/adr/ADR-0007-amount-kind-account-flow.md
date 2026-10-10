# ADR-0007 — 扩展金额 kind：账户流入与提供资金

> 状态：Accepted（架构口径）。引用这两类金额的规则版本仍为 `pending`，未经 `signoff()` 不进入有效视图。
> 扩展 ADR-0003。ADR-0003 的六类及 `component_of` 去重规则继续有效。

## Context

2026-10-10 补充需求要求情节严重路径 S3、S6、S7 使用独立金额口径。ADR-0003 把 `app.case_amount.kind` 定为六类封闭 CHECK，Java `FactsBaselineService.AMOUNT_KINDS` 使用同一集合。支付结算金额不能代替提供资金，账户流入也不能代替违法所得或上游犯罪金额。

## Decision

1. 封闭集增加两类，仍由 CHECK 约束，不改为字典表，不使用 PostgreSQL ENUM：
   - `account_total_flow`：经核实的账户流入资金，用于 S6、S7。
   - `provided_funds_amount`：行为人实际提供的资金，用于 S3。
2. 新增 kind 的路径仍是：需求确认 → 本 ADR → 前向迁移 `V27__amount_kind_account_flow.sql` → 应用层枚举。不得绕过 CHECK。
3. `account_total_flow` 按行记录 `accountOwnership`（或 `attributes.accountOwnership`）：
   - `self`：本人账户，聚合为 `amounts.account_total_flow.confirmedSumSelf`。
   - `non_self`、`unit`：非本人账户或单位账户，聚合为 `confirmedSumNonSelf`。
   - 未识别的归属不进入上述两个子集，也不改写该 kind 的 `confirmedSum`。
4. 同一 kind 内继续按 ADR-0003 / INV-DATA-001 对 `component_of` 去重。不同 kind 不得互相折算。不同行为人的流水不得合并进同一统计行。
5. 只有 `verificationStatus=confirmed` 的金额进入 `confirmedSum*`。候选、冲突和未确认金额不参与门槛。

## Consequences

- 已有六类金额的读写和求和不变。
- S6、S7 不得读取未按归属拆分的 `confirmedSum` 来判断。
- 前端遇到封闭集之外的 kind，仍显示原文并标为未识别口径。

## Alternatives Considered

- 只用事实字段存放 5 万元和 30 万元，不扩展 kind：精度、币种、证据和去重会弱于现有金额体系。
- 把单位账户单独做成第三套求和：S7 的文本已把单位账户纳入非本人账户路径，先归入 `non_self`。若后续会签要求分开统计，再增聚合字段，不回头改 V27 的 kind 名单。
