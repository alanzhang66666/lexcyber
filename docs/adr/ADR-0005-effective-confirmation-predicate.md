# ADR-0005 — 「有效确认」判定与 stale 充分性

> 状态：Accepted。裁决 v1.3 内部矛盾 #5（§5.9 公式 vs §4.8.3 附加校验 vs §4.11 措辞）。

## Context

三处对「某模块的确认当前是否有效」给出不同强度的定义：

- §5.9：`is_effectively_confirmed = confirmed_version_id != null && stale == false`
- §4.8.3：批准事务内还要校验「dependency snapshot 仍有效」「不是 blocked」「Review 未 superseded」等
- §4.11：「`stale` + dependency validation」

关键分歧：`stale` 标志是否**充分**？若不充分，下游读取会因漏判而放行本应失效的确认；若充分，§4.8.3 的额外校验是冗余但安全的防线。

## Decision

1. **`stale` 是权威且充分的判定字段。** `is_effectively_confirmed` / `is_effectively_approved` 仅以 `*_version_id != null && stale == false` 判定，与 §5.9 一致。
2. 充分性由 `StalePropagationService` 保证：任何使确认失效的事件（新 FactsVersion 确认、上游 ArtifactVersion 新确认、规则/法源/模板失效）**必须**在同一事务内把对应 Head 置 stale。遗漏 propagation 是缺陷，不是可容忍窗口。
3. §4.8.3 中批准时的「dependency snapshot 仍有效」等校验保留，但定位为**防御性第二道防线**——它们验证 stale 传播没有漏网，不是谓词的一部分。若这些校验失败而 stale=false，说明传播逻辑有 bug，应告警并阻断，不是「正常失败路径」。
4. §4.11 的「stale + dependency validation」读作：stale 字段是判定主键，dependency validation 是批准时刻的校验动作，二者不并列成「或」的关系。

## Consequences

- `ModuleConfirmationService.requireEffectiveConfirmation` 的实现就是 §5.9 公式，不另加查询。
- 下游 Controller / SQL / Engine adapter 不得自行拼「确认是否有效」逻辑（INV-PIPE-003）。
- stale 传播的正确性必须有专项测试覆盖（v1.3 §19.12/19）。

## Alternatives Considered

- 「读时校验依赖」：每次读取都递归校验依赖快照——正确性强但每次读都要走依赖图，且「何时算失效」难以与并发写入对齐。
- 「批准时才发现失效」：把 §4.8.3 校验当唯一防线——会让 stale=false 的失效确认在批准前一直被读侧认为是有效的，下游漏判窗口更大。

## Migration / Compatibility Notes

- `StalePropagationService` 必须在 FactsVersion 确认、ArtifactVersion 发布、规则/法源/模板失效三个入口都被调用。
- 防御性校验失败时记 `business_audit` + 返回 `409`，不静默放行。
