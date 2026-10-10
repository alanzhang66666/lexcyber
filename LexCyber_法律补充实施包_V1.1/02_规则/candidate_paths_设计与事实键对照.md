# candidate_paths 正式语料声明说明

## 当前执行器限制

`engine/rules/conviction_paths.py` 仅执行 `outcome.candidate_paths` 的**显式定义**，不会把旧 `charge_candidate`、`distinction` 或文本说明自动转为路径。路径要求唯一 actor 绑定与 confirmed 证据，否则返回 blockers。

## 必须审核的路径

- `assisting_information_network_crime`：帮信候选与要件不满足时的待核查/已确认排除。
- `concealing_criminal_proceeds`：掩隐候选，不能把上游既遂等同于完整要件。
- `fraud_accomplice`：诈骗共犯候选，具体明知和实质参与必须可被证明。

每条 `candidate_paths` 声明至少包含：`path_id`, `label`, `charge_key`, `actor_fact_key`, `supporting_fact_keys`, `contrary_fact_keys`, `when_true`, `when_false`, `subjective`。分支字段 `baseline_position` 只允许 `candidate / alternative_to_examine / excluded`；排除必须有非空 `exclusion_reason` 且关联反证键，候选必须有关联支持事实键。

**禁止**仅因规则 false 就生成 `excluded`。在事实键缺失/证据冲突/时间冲突/法源不足时应保持 blocked、待查或候选，不生成可供依赖的终局排除理由。

`actor_fact_key` 必须对应唯一 confirmed 事实，并用 actorId 解析到冻结快照的唯一参与人；支持/反证事实证据应同属对应主体。`charge_key` 必须通过同一时点 `coverage.covers` 的明确法学映射；引擎不得自行创造近邻罪名映射。

## 绑定映射待补的事实字段

| 路径 | 支持事实建议 | 相反事实建议 | 审核难点 |
|---|---|---|---|
| 帮信 | upstream_crime_established, knowledge_of_crime, help_type, severity_met | factual_negation_* | 严重情节由独立规则汇总，不用单证否定 |
| 掩隐 | upstream_crime_completed, involvement_after_completion, knowledge_of_criminal_proceeds, transfer_behavior | prior_collusion, assistance_started_before_completion | 既遂不是掩隐充分条件 |
| 诈骗共犯 | specific_knowledge, prior_collusion 或 stable_cooperation_before_completion, substantive_participation | merely_general_knowledge, occasional_support | 具体明知和长期固定、实质参与须证据充分 |

**这些是事实键设计建议，不是现有仓库已确认存在的键。** 需要法学负责人和工程根据冻结事实字典裁定后写入正式 `candidate_paths` 语料。

## 验收

- 完整路径：各自 actorId、支持证据、反证、规则版本、法源版本、时点可追溯。
- 缺少主体绑定或证据：阻断而非伪造证明。
- 正反证据冲突：conflicted 而非排除。
- 显式请求的罪名无 coverage：返回 `CHARGE_OUT_OF_COVERAGE`，不得近似匹配。
- 不同时点的路径独立计算，不得跨时点自动补齐。
