# ADR-0006 — archive_version 用 cases.next_archive_version 计数器

> 状态：Accepted。裁决 v1.3 内部矛盾 #6（§4.8.6 用 `MAX(version)+1`，违背 INV-DB-SOURCE-001）。

## Context

v1.3 §4.8.6 第 8 步写「`archive_version` = 当前同案最大版本 + 1（受 case 行锁保护）」。这与 INV-DB-SOURCE-001「不得通过扫描历史猜当前值」以及 §4.6.4 对 `artifact_stream.next_version` 的计数器模式不一致。

行锁下的 `MAX+1` 在并发上是安全的（锁保证了无竞态），但它把「下一个版本号」这个事实只存在于历史扫描里，违反了「单一事实源」原则；一旦某次归档因错误被部分回滚后又重试，扫描语义也会更脆弱。

## Decision

1. `app.cases` 增加 `next_archive_version integer NOT NULL DEFAULT 1 CHECK (next_archive_version > 0)`。
2. 归档事务内：
   ```text
   SELECT app.cases ... FOR UPDATE      // 行锁即版本分配锁
   archive_version = cases.next_archive_version
   INSERT case_archive ...
   UPDATE app.cases SET next_archive_version = next_archive_version + 1
   COMMIT
   ```
3. `UNIQUE (case_id, archive_version)` 作为结构兜底。

## Consequences

- 归档版本分配与 artifact 版本分配同构，统一心智模型。
- `next_archive_version` 只在锁内推进；并发归档请求串行化。
- `case_archive` 仍 insert-only；版本号分配器不回退（即使归档失败已占用一个版本号，跳过即可，不复用）。

## Alternatives Considered

- 维持 `MAX+1`：能用但违背 INV-DB-SOURCE-001，且把版本分配逻辑散到 SQL 里而非显式字段。
- 独立 `archive_version_seq` 序列表：为每案一行等价于在 cases 上加列，但没有额外收益。

## Migration / Compatibility Notes

- `cases.next_archive_version` 默认 1；已有数据无需回填。
- `UNIQUE (case_id, archive_version)` 与 `UNIQUE (case_id, manifest_hash)` 并存（§4.6.11）。
