> **归档文档（历史）**：本文件已于 2026-09-26 移入 docs/archive/，内容反映其写作时点状态，可能与现行实现不一致。现役入口见根 README.md 与 AGENTS.md。

# 远端仓 vs 本地对比与迁入建议

核对时间：2026-09-18 · 基准：本地 `main` = `origin/main` = `13c5ed4`（已 fetch 对齐）

## 结论

| 方向 | 状态 |
| --- | --- |
| `main` ↔ `origin/main` | 完全同步，无领先/落后提交 |
| 远端有、本地没有 | 2 个开放 PR：`feat/t3-round3`（PR #10，3 提交）、`feat/t2-round2`（PR #11，3 提交） |
| 本地有、远端没有 | 工作区未提交改动约 +2009/-211 行：`case-import.v1` 协作导入线（后端为主） |
| 冲突风险 | **有**。本地未提交改动与 `feat/t3-round3` 在 5 个文件上重叠，且是不同内容的并行修改 |

## 一、远端领先 main 的内容（候选迁入）

### 1. `origin/feat/t3-round3`（PR #10 OPEN）— 建议迁入，需处理冲突

3 个提交：`resolve reviewed amount and jurisdiction gaps`、`register section six sentencing outlines`、`replay reviewed sentencing dispositions`

内容：三案金额与管辖口径经法学复核后的落地；第六部分宣告刑建议重放；`sources`/`sentencing` 适配器补强。

| 文件 | 改动 | 与本地工作区重叠 |
| --- | --- | --- |
| `engine/adapters/sentencing.py` | +113 行（宣告刑重放、规则校验） | 无（本地未改） |
| `engine/adapters/case_bundle.py` | +68 行（`included_in_amount_id`、`calculation_rule`、double-counted 校验） | **有** |
| `engine/adapters/t1_contract.py` | +7 行（`calculationMode`/`termRangeMonths`/`fineRangeCny` 等投影字段） | **有** |
| `demo_cases/three_case_demo/case-{a,b,c}.json` | 三案数据更新 | 无（本地只改了 index/README） |
| `demo_cases/three_case_demo/index.json` | `dataset_id` → `...-09-18` | **有**（本地加了 `producer_id`/`revision`/`external_case_id`） |
| `demo_cases/three_case_demo/README.md` | 更新 | **有** |
| `tests/unit/test_t3_three_case_demo.py` | +161 行（重放测试） | **有**（本地改写了 module content 测试） |
| `docs/t3-three-case-handoff.md` | 更新 | 无 |

语义上两边改的是**不同关注点**（T3 加金额/管辖/重放，本地加导入身份与 schema 校验），可共存，但文本级会冲突，需手工三方合并。

### 2. `origin/feat/t2-round2`（PR #11 OPEN）— 可直接迁入，无冲突

3 个提交：`补全版式组件和logo`、`增加ui设计`、分支自合并。

只动 `web/`：`assets/logo.png`（新增）、`style.css`、`CaseWorkspacePage.vue`、`HomePage.vue`。与本地工作区零重叠（本地只碰了 `web/src/lib/module-content.test.ts`）。

## 二、本地领先远端的内容（未提交）

`case-import.v1` 协作案件包导入，约 +2009 行，全部未提交：

- 契约：`public-api.yaml` 8 个 `imports` 端点、`contracts/schemas/` 3 个 JSON Schema、`docs/case-import-v1.md`
- Java：`server/imports/` 约 30 文件、`ImportController`、`EngineImportClient`；迁移 `V10`（幂等表）、`V11`（import staging + 租约）
- Engine：`import_package.py`、`t1_contract.py` +230、`api.py` +104、`import_three_case_demo.py` +1139
- 测试：`test_import_package.py`、`test_import_three_case_demo.py`；pytest 83 过 1 跳；Java 回归容器 61 测试过
- **未收口**：最新语义复审 NEEDS_CHANGES，2 个已确认 high（stale worker 重放 step 动作；ZIP 提取内存超限）
- 杂项：`.tmp-*.txt`、 untracked `semantic-review/`、根目录两个中文名计划文档未跟踪

## 三、可忽略的分支

以下远端分支已被 main 包含或明显过期，无需迁入：

- `origin/feat/t3-round2`、`origin/feat/t1-round2`、`feat/t1-round1`、`feat/t2-round1`、`codex/t1-api01-document-link`、`pr/5-document-link`：已合并
- `origin/dev`（落后 34）、`origin/feat/frontend-design-system`（落后 35）：过期

本地 `feat/t1-round2` 显示 "ahead 2" 是假象——`2c6ea1f`、`8a70b1c` 已合并进 main，该本地分支可删。

## 四、建议迁入顺序

1. **先保护本地 import 工作**：当前改动挂在 main 工作区，迁入远端前必须落袋。建议
   `git checkout -b feat/case-import && git add -A && git commit`（`.tmp-*`、`semantic-review/`、根目录临时文档视需要 `.gitignore` 或排除）。
2. **迁 `feat/t2-round2`**（无冲突）：等 PR #11 合入后 `git pull`；或本地 `git merge origin/feat/t2-round2` 先验。
3. **迁 `feat/t3-round3`**（有冲突）：建议等 PR #10 合入 main 后，在 `feat/case-import` 上 `git rebase main`（或 merge），手工处理 5 个重叠文件：
   - `index.json`：两边都要——本地的 `producer_id`/`revision`/`external_case_id` + 远端的 `dataset_id` 09-18
   - `case_bundle.py`：本地的 jsonschema 校验 + 远端的金额/管辖校验，函数级可并存
   - `t1_contract.py`：本地的 `case.module.content.v1` 投影 + 远端的量刑结果字段投影
   - `test_t3_three_case_demo.py`：本地 module content 测试 + 远端重放测试，按用例合并
   - `README.md`（demo）：按最新口径合并
4. **合入前必做**：先修掉语义复审的 2 个 high，并同步 `web/src/api-types.ts` 契约快照（README 硬性要求）。
5. 反方向：import 线收敛后再推送为远端 PR，不要在当前工作区状态下直接推 main。

## 五、遗留确认项

- `feat/t3-round3` 的 `dataset_id` 升到 `...-09-18` 与本地 `revision: "2026-09-17.1"` 是否要保持同一命名口径，合并时需统一。
- `semantic-review/` 复审记录是否纳入版本管理（当前 untracked）。
