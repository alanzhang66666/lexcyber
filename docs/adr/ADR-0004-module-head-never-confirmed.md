# ADR-0004 — ModuleHead 区分「从未确认」与「确认已失效」

> 状态：Accepted。裁决 v1.3 内部矛盾 #4（§4.6.7 CHECK 允许 `stale=true, stale_reason=NULL`，与「stale 必有因」语义冲突）。

## Context

`module_head.stale` 默认 `true`，CHECK 只要求 `stale = false` 时 `stale_reason IS NULL`。因此 `stale=true, stale_reason=NULL` 是合法行——但它混淆了两个语义完全不同的状态：

- **从未确认**：`confirmed_version_id IS NULL`，没有需要失效的确认；
- **确认已失效**：`confirmed_version_id` 指向某版本但 `stale=true`，stale_reason 说明失效原因。

下游界面与归档门闩必须区分二者：前者是「该模块还没有可用结论」，后者是「曾有结论但已失效」。

## Decision

1. 「从未确认」由 `confirmed_version_id IS NULL` 表达，不占用 `stale_reason`。
2. CHECK 修正为：

   ```sql
   CONSTRAINT ck_module_head_stale_consistency CHECK (
     (confirmed_version_id IS NULL AND stale = true AND stale_reason IS NULL)
     OR
     (confirmed_version_id IS NOT NULL AND (
       (stale = false AND stale_reason IS NULL)
       OR
       (stale = true AND stale_reason IS NOT NULL)
     ))
   )
   ```

3. `DraftHead` 采用同构规则（`approved_version_id IS NULL` + stale/stale_reason 三态一致）。

## Consequences

- `is_effectively_confirmed = confirmed_version_id IS NOT NULL AND stale = false` 保持 §5.9 公式不变。
- 「从未确认」的模块天然 stale=true，归档门闩与下游门闩读同一字段即可。
- 任何把 `confirmed_version_id` 置 NULL 来表达「失效」的代码违规（INV-MODULE-003）。

## Alternatives Considered

- 引入 `never_confirmed` 布尔标志：冗余，可由 `confirmed_version_id IS NULL` 推导。
- 允许 stale_reason 在 confirmed_version_id IS NULL 时也填值：会制造「无对象可失效却有失效原因」的矛盾态。

## Migration / Compatibility Notes

- 回填规则：`case_module_states.status='confirmed'` → `confirmed_version_id` 指向迁出的 artifact version、`stale=false`；否则 `confirmed_version_id=NULL, stale=true, stale_reason=NULL`。
