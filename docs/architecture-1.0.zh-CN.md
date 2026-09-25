# LexCyber 系统架构书（理想态）

> **⚠️ 已被取代。** 目标架构以 `LexCyber-system-architecture-v1.3-postgresql-physical-model.md`（仓库根）为准；
> 本文保留作历史草稿。本文与 v1.3 冲突处以 v1.3 为准。实施状态见 `docs/architecture-roadmap.md`。
>
> 读者：T1 / T2 / T3 工程团队
>
> 本文不含任何交付状态、日期、flag 开关情况。状态见 `lexcyber-0.8.zh-CN.md`。
> 本文出现「必须 / 不得」即为不变量，破坏需三方会签。

---

## 第 0 章 定位

可审计的刑事研判工作台。覆盖范围：**帮助信息网络犯罪活动罪及其邻近罪与上下游罪**。

系统产出**带证据、带法源版本、带计算过程的候选结论**，交由具资格的人审确认。系统**不得**产出终局的量刑、责任或犯罪结论。

---

## 第 1 章 不变量

全书最高层。任何模块设计与之冲突，改模块，不改本章。

### 1.1 失败闭合（Fail-closed）

**每一个计算单元的返回必须是三态之一**：`calculated` / `blocked` / `not_applicable`。不存在「部分成功」。

`blocked` 的载荷形状全系统统一：

```
blockers: [{ code, path, message, retryable }]
```

`path` 必须是**可定位到输入字段的 JSON 路径**（`rule.adjustments[2].source_ids`），不是自然语言描述。前端据此高亮字段，不做字符串匹配。

**不变量 1.1.1**：任何 `calculated` 结果必须携带 `human_review_required: true`。系统没有「自动通过」路径。

**不变量 1.1.2**：输入不合格时**不得**降级产出。宁可 `blocked`，不可给一个标了「仅供参考」的数。

### 1.2 可解释性

**不变量 1.2.1**：任何数值结论必须附 `steps[]`，每步含 `before → delta → after` 与 `source_ids[]`。

**不变量 1.2.2**：任何定性结论必须附 `supporting_evidence_ids[]` **与** `contrary_evidence_ids[]`。相反证据为空是合法的，但字段**不得缺省**——缺省和「已查无相反证据」是两件事。

**不变量 1.2.3**：`source_ids` 指向的必须是**带版本的法源条目**，不是法条名称字符串。

### 1.3 法源时效

**不变量 1.3.1**：每条法源必须有 `source_version`、`effective_from`、`effective_to`（现行为 `null`）。

**不变量 1.3.2**：一切检索与规则选取必须显式传 `as_of_date`。**不得**存在隐式「用最新版」的调用路径。

**不变量 1.3.3**：当**行为时法**与**裁判时法**给出不同结论时，系统必须**并列输出两条路径**并置 `blocker: law_version_divergence`，交人审选择。**不得**自行择一。

> 这是本系统最核心的差异化能力。新旧掩隐解释（法释〔2015〕11 号 `effective_to: 2025-08-25` vs 法释〔2025〕13 号 `effective_from: 2025-08-26`）是该机制的第一个实例。

### 1.4 数据分类

**不变量 1.4.1 金额口径不可互换。** 每个金额必须有 `kind`，各类**分开存储、分开展示、禁止求和跨类**。已确认的类别至少包括：

| kind | 说明 |
|---|---|
| `payment_settlement_amount` | 支付结算金额（帮信「情节严重」要件） |
| `illegal_gain` | 违法所得 |
| `crime_amount` | 上游犯罪金额 / 被害人损失 |
| `business_revenue` | 经营性收入（**不入罪量评价**） |
| `recovery` | 追缴数额 |
| `fine` | 罚金 |

> 反例约束来自 A 案：28 万元是设备销售经营收入，**不是**支付结算金额、**不是**犯罪所得；冯某个人 3 万元才是违法所得；96 万元是上游诈骗金额。三者不得相加、不得替换。
> C 案追加约束：**组成关系不得重复相加**（9.8 万是 11.8 万的组成部分）。因此金额实体必须支持 `component_of` 引用。

**不变量 1.4.2 核验状态是五态，不是布尔**：

```
candidate | baseline_asserted | confirmed | rejected | conflicted
```

`baseline_asserted`（基准位置）**不得**在任何界面渲染为「已审核结论」。`conflicted` 必须同时展示双方证据，**不得**折叠。

### 1.5 审计与版本

**不变量 1.5.1**：复核绑定**一个不可变结果版本**。批准只确认该版本，**不得**恢复或重跑执行。

**不变量 1.5.2**：重试创建**新执行**，旧结果、审计与决定全部保留。

**不变量 1.5.3**：被复核对象的新版本发布时，旧版本上 pending/approved 的复核自动 `superseded`，**不得**静默继承批准。

**不变量 1.5.4**：确认即锁。`facts` confirm 后 `PUT` 返 `409`；模块 confirmed 后 `PUT` 返 `409 MODULE_CONFIRMED`。解锁需显式新版本，不是原地改。

### 1.6 边界

| 规则 | 内容 |
|---|---|
| 浏览器 | 只访问 Nginx 暴露的 `/v1`。**不得**直连 Engine / PostgreSQL / Redis / MinIO / 向量库 |
| 内部调用 | Java → Engine 必须 `X-Service-Token` |
| 对象键 | 客户端**不得**发送 `storageKey`。服务端从属主材料覆写；伪造键被忽略 |
| schema 所有权 | `app` 归 Java，`engine` 归 Python。**不得**跨 schema 直读 |
| 模型访问 | 只有 `ModelGateway` 可调外部模型 API |
| 队列 | Redis 只承载执行号。结果与复核状态持久在 PostgreSQL |
| 迁移 | 只走 Flyway，前向唯一。**不得**修改已发布迁移 |

### 1.7 幂等与并发

**不变量 1.7.1**：一切创建型写入接受 `Idempotency-Key`，服务端持久绑定请求内容与返回资源。同一身份重放返回同一资源。

**不变量 1.7.2**：执行租约带 fencing token。过期 token **不得** claim 或 complete。

---

## 第 2 章 领域模型

```
Account
 └─ Case ──────────────────────────────────────┐
     ├─ Document ── ParseResult(document.parse.v1)
     ├─ Actor          （自然人 / 单位）
     ├─ Event          （时间 / 阶段 / 主体 / locator）
     ├─ Evidence       （quote / locator / documentId）
     ├─ Fact           （stage / statement / verification_status / evidence_ids）
     ├─ Amount         （kind / value / component_of / verification_status）
     ├─ ModuleState    （五段各一份：applicability / status / version / content）
     ├─ CandidatePath  （label / baseline_position / supporting / contrary / legal_source_ids）
     ├─ JurisdictionConnection（type / value / verification_status）
     ├─ MissingItem    （severity / description）
     ├─ Draft          （templateId / fieldValues / renderedObjectKey / version）
     └─ ReviewRecord   （target / resultVersion / status / decision / archiveStatus）

LegalSource（全局，非案件级）
     └─ source_version / effective_from / effective_to / authority / aliases

SentencingRule（全局，非案件级）
     └─ rule_version / legal_review_status / base_months / adjustments[] / bounds / source_ids
```

### 2.1 两条必须区分的轴

| | 案件轴 | 规则轴 |
|---|---|---|
| 实体 | Case 下全部 | `LegalSource`、`SentencingRule`、`DocumentTemplate` |
| 版本语义 | 案件事实变化 | 法律/规则变化 |
| 会签主体 | 个案办案人 | 法学负责人 |
| 变更影响 | 单案 | **全部引用该版本的案件** |

**不变量 2.1.1**：规则轴的版本变更**不得**回溯改写已确认的案件结论。已确认结论冻结其引用的 `source_version` / `rule_version` 快照。

**不变量 2.1.2**：案件事实变更时，依赖它的模块状态必须置 `factsStale: true`，但**不得**自动清空或重算。

### 2.2 schema 冻结后的约束

现状 `module-content.ts` 对每个字段尝试多个候选 key（因 T3 的精确 JSON key 尚未会签）。

**理想态：schema 冻结后，多 key 容错层必须删除。** 架构上多 key 容错是**缺陷**——它让 schema 违规静默通过。冻结后应改为 schema 校验失败即 `blocked`。

---

## 第 3 章 五段管道

每段固定五栏。**这五栏是模板，新增模块照填。**

### 3.1 管道总览

```
材料 → 解析 → 事实确认 ──┬─→ ① 合规筛查 ─→ ② 定罪研判 ─→ ③ 量刑分析 ─→ ④ 文书生成 ─→ ⑤ 复核归档
                          │       │              │              │              │              │
                          └───────┴──────────────┴──────────────┴──────────────┴──────────────┘
                                          任一段均可独立开单复核（第 3.7 节）
```

**不变量 3.1.1**：③ 量刑要求 ② 定罪已 confirmed。② 要求 `facts` 已 confirmed。④ 要求 ③ 已产出 `calculated` 或人审已定值。**门闩不得跳过**，违反返 `409`。

**不变量 3.1.2**：① 合规的 `applicability` 可为 `not_applicable`，此时管道**跳过**该段而非阻断。`not_applicable` 必须有理由与证据。

### 3.2 ① 合规筛查

| | |
|---|---|
| **输入** | confirmed facts、events、evidence、actors（含单位主体）、amounts |
| **计算归属** | Engine 规则引擎 `ComplianceRuleEngine`。**不使用 LLM 产出结论。** |
| **产出** | `case.compliance.v2`：`checklist[]`（category / status / evidence_ids / rule_id / source_ids）、`risk_timeline[]`、`missing_items[]` |
| **门闩** | facts 未 confirmed → `409 FACTS_NOT_CONFIRMED`；规则版本未 approved → `blocked: rule_not_approved` |
| **人审** | `ReviewTarget{kind: module, module: compliance, version: n}` |

规则形状与量刑同构：

```
ComplianceRule {
  rule_id, rule_version, legal_review_status: approved,
  source_ids: [...],                    // 必填，非空
  dimension,                            // 制度 / 岗位 / 培训 / 审查 / 报告 / 处置
  predicate,                            // 对 facts/amounts 的确定性判定
  outcome_status,                        // 该维度客观状态
  required_evidence_kinds: [...]
}
```

**不变量 3.2.1**：`checklist[].status` 是**客观状态**（如「已建立未执行」），**不得**是风险评分或分级。系统不产出合规风险分数。

### 3.3 ② 定罪研判

| | |
|---|---|
| **输入** | confirmed facts、subjective_knowledge facts、amounts（按 kind）、jurisdiction_connections、①（若适用） |
| **计算归属** | Engine 规则引擎 `ConvictionRuleEngine` |
| **产出** | `case.conviction.v2`：`candidate_paths[]`、`jurisdiction_connections[]`、`missing_items[]`、`law_version_divergence[]` |
| **门闩** | facts 未 confirmed → `409`；① 适用但未 confirmed → `409`；管辖连接点全部未核实 → `blocked: jurisdiction_unestablished` |
| **人审** | `ReviewTarget{kind: module, module: conviction, version: n}` |

**不变量 3.3.1 必须产出多路径。** 单一路径的输出视为缺陷。每条路径：

```
CandidatePath {
  actor_id, label,                      // 罪名
  baseline_position,                    // selected | alternative_to_examine | excluded
  supporting_evidence_ids: [...],
  contrary_evidence_ids: [...],         // 字段不得缺省
  legal_source_ids: [...],              // 带 source_version
  exclusion_reason                      // excluded 时必填
}
```

**不变量 3.3.2 排除路径必须保留。** A 案排除了「诈骗罪共同犯罪」与「单位帮信罪」，这两条**必须出现在输出里**并带排除理由与相反证据。删掉排除路径等于删掉研判过程。

**不变量 3.3.3 界分规则必须独立可寻址。** 帮信 vs 掩隐、帮信 vs 诈骗共犯 的界分是**规则实体**，不是某条路径的附注。界分规则必须绑法发〔2025〕12 号、法发〔2016〕32 号等具体条目。

**不变量 3.3.4 主观明知不得由金额单独推定。** 明知推定规则（法释〔2019〕15 号第十一条）必须保留「相反证据审查」分支。存在相反证据时状态为 `conflicted`，不是 `confirmed`。

**罪名覆盖范围（理想态目标集）**

| 层 | 罪名 | 条 |
|---|---|---|
| 核心 | 帮助信息网络犯罪活动罪 | 287 之二 |
| 邻近 | 非法利用信息网络罪 | 287 之一 |
| 邻近 | 掩饰、隐瞒犯罪所得、犯罪所得收益罪 | 312 |
| 上游 | 诈骗罪 | 266 |
| 上游 | 开设赌场罪 | 303 II |
| 下游 | 洗钱罪 | 191 |
| 关联 | 妨害信用卡管理罪 | 177 之一 |
| 关联 | 侵入 / 破坏计算机信息系统罪 | 285 / 286 |
| 管辖 | 属地 / 属人管辖 | 6 / 7 |

**不变量 3.3.5**：语料未覆盖的罪名**不得**输出为候选路径。必须返回 `missing_item: charge_out_of_coverage` 并列明请求的罪名。**不得**用相近罪名替代。

### 3.4 ③ 量刑分析

| | |
|---|---|
| **输入** | confirmed ② 的 selected path、按 kind 的 confirmed amounts、量刑情节 facts、`as_of_date` |
| **计算归属** | Engine `SentencingRuleEngine`（`calculate_sentencing` 算术分支即为其内核） |
| **产出** | `sentencing.result.v2`：`term_months` / `term_range_months`、`fine`、`recovery_cny`、`steps[]`、`rule_version`、`source_ids`、`input_snapshot` |
| **门闩** | ② 未 confirmed → `409`；规则或任一调节项未 approved → `blocked`；任一参数非 confirmed 或无 `evidence_ids` → `blocked` |
| **人审** | `ReviewTarget{kind: module, module: sentencing, version: n}`，**强制**（`human_review_required` 恒为 true） |

**计算模式必须显式声明** `calculation_mode`：

| mode | 语义 | 可否作为系统结论展示 |
|---|---|---|
| `explainable_calculation` | 规则引擎按起点+调节比例推算 | 可，须附完整 `steps[]` |
| `reviewed_disposition_replay` | 重放法学已审阅宣告刑 | 可，须标注为已审阅建议 |
| `dual_track` | 上两者并列 | 可，差异必须触发复核 |

**不变量 3.4.1**：`calculation_mode` **不得**缺省。前端**不得**将两种模式渲染成同一种视觉。

**不变量 3.4.2**：调节项运算符封闭集 `fixed_months | percent_of_base | percent_of_current`。未知运算符 → `blocked: operation_unsupported`，**不得**忽略跳过。

**不变量 3.4.3**：`percent_of_current` 依赖调节项顺序，因此 `adjustments[]` 的**顺序本身是规则内容**，必须随 `rule_version` 冻结。

**不变量 3.4.4**：`minimum_months` / `maximum_months` 夹逼必须来自法定刑幅度且绑法源。夹逼生效时必须在 `steps[]` 留一步，**不得**静默截断。

### 3.5 ④ 文书生成

| | |
|---|---|
| **输入** | ①②③ 已 confirmed 的结论、案件主体与事实、`DocumentTemplate` |
| **计算归属** | Engine `DocumentRenderer`（**服务端渲染**，非前端拼字符串） |
| **产出** | `draft.v2`：`templateId` / `templateVersion` / `fieldValues` / `renderedObjectKey`（MinIO 中 DOCX） / `unresolvedPlaceholders[]` / `version` |
| **门闩** | 见下 |
| **人审** | `ReviewTarget{kind: draft, draftId, draftVersion}` |

模板实体：

```
DocumentTemplate {
  template_id, template_version,
  legal_review_status,                  // 模板"已提供" ≠ 字段映射"已会签"
  source_object_key,                    // 法学提供的 DOCX
  fields: [{ name, required, source_binding, type }],
  branches: [{ condition, fields }],
  placeholder_syntax: "【…】"
}
```

**不变量 3.5.1 占位符阻断在服务端。** 渲染后正文含任何未替换 `【…】` → `blocked: unresolved_placeholder`，`path` 指向具体占位符。前端的 `【待补充】` 检查是**冗余提示**，不是防线。

**不变量 3.5.2**：必填字段缺失、条件分支未选定 → `blocked`。**不得**填入默认值或空串。

**不变量 3.5.3**：`fieldValues` 只能取自 **confirmed** 的案件数据。引用 `candidate` / `conflicted` / `baseline_asserted` 数据 → `blocked: field_source_unconfirmed`。

**不变量 3.5.4**：`template.legal_review_status != approved` 时**可以渲染预览，但不得批准**。预览产物必须带不可去除的水印标识。

### 3.6 ⑤ 复核归档

| | |
|---|---|
| **输入** | 任一 `ReviewTarget` + 其不可变版本 |
| **计算归属** | Java（**不派发 Engine**） |
| **产出** | `ReviewRecord`：`target` / `resultVersion` / `status` / `decision` / `actor` / `comment` / `archiveStatus` / `returnTarget` |
| **门闩** | 属主案件校验。非属主或不存在 → `404`（**不得** `403`，避免存在性泄露） |
| **人审** | 本段即人审 |

### 3.7 统一复核目标抽象

现状是三种机制：module 走 `module_state` 枚举、量刑走 task、文书走 draft。理想态收敛为一个多态目标：

```
ReviewTarget =
  | { kind: "module", module: compliance | conviction | sentencing, version: int }
  | { kind: "draft",  draftId: string, draftVersion: int }
  | { kind: "task",   taskId: uuid, resultVersion: int }
  | { kind: "parse",  documentId: string, resultVersion: int }
```

**不变量 3.7.1**：`ModuleStateView.module` 枚举必须扩为 `[compliance, conviction, sentencing]`。量刑不再只能经 task 复核。

**不变量 3.7.2**：`module` 派生逻辑**必须只有一处实现**。写入时确定，读取时不推导。

**不变量 3.7.3**：`returnTarget` 必须能把复核人一键送回被复核对象的**那个版本**的视图，不是当前版本。

---

## 第 4 章 服务架构

```
Browser
  │ 只 /v1
  ▼
Nginx ──┬─→ web (Vue 静态)
        └─→ Java 公开 API ─┬─→ PostgreSQL  schema app
                           ├─→ MinIO       原文 + 渲染产物
                           └─→ Engine 内部 API  (X-Service-Token)
                                    │
                                    ├─→ Redis / Dramatiq   (只传执行号)
                                    ├─→ PostgreSQL schema engine  (租约 / checkpoint / 技能执行记录)
                                    ├─→ MinIO  (回读字节 / 写渲染产物)
                                    └─→ ModelGateway ─→ 外部模型 API
```

### 4.1 职责

| 层 | 拥有 | 明确不拥有 |
|---|---|---|
| Java | 公开契约、鉴权与属主、案件/材料/事实、任务生命周期、结果版本、复核、业务审计、对象写入边界 | 任何法律规则判断 |
| Engine | 执行租约、阶段 checkpoint、解析、**四个规则引擎**、模板渲染、模型调用、Engine 审计 | 公开契约、鉴权、属主判定 |
| 规则层 | 合规 / 定罪 / 界分 / 量刑规则，法源语料，模板字段字典 | 案件数据 |

**不变量 4.1.1**：规则层是 Engine 内的**独立子系统**，其版本与代码版本解耦。规则更新**不得**要求发版。

**不变量 4.1.2**：Java **不得**内嵌任何法律判断。能力门闩只做开关，不做法律推理。

### 4.2 模型的位置

规则引擎产出结论。模型**只允许**用于三件事：

1. 从解析正文中**抽取候选**事实 / 主体 / 事件 / 金额 → 一律落 `candidate`，**不得**落 `confirmed`
2. 为已由规则引擎确定的结论**生成叙述文字**
3. 语义检索的召回辅助（排序仍由 `as_of_date` + 权威层级决定）

**不变量 4.2.1**：模型输出**不得**直接成为 `candidate_paths`、`checklist[].status`、`term_months` 或任何 `source_ids`。
**不变量 4.2.2**：模型生成的叙述与规则产出的结论**必须分字段存储**，前端必须可视区分。
**不变量 4.2.3**：模型每次调用留审计记录（provider / model / 版本 / 输入哈希 / 输出哈希）。

---

## 第 5 章 法源与知识层

### 5.1 法源条目

```
LegalSource {
  id, title, document_number, article,
  jurisdiction, authority,              // law | judicial_interpretation
                                        // | normative_opinion | sentencing_guidance
  source_version,
  effective_from, effective_to,         // null = 现行
  official_url, excerpt, aliases: [...],
  superseded_by: [...], supersedes: [...]
}
```

**不变量 5.1.1**：`authority` 决定冲突时的优先级，**不得**由 `effective_from` 新旧决定。

**不变量 5.1.2**：`supersedes` / `superseded_by` 必须显式建链。法释〔2025〕13 号废止法释〔2015〕11 号，这条关系是**数据**，不是注释。

### 5.2 时效比对引擎（本系统核心能力）

```
resolve(query, as_of_date, conduct_date, judgment_date)
  → { conduct_law: [...], judgment_law: [...], divergence: [...] }
```

**不变量 5.2.1**：`conduct_date` 与 `judgment_date` 落在同一法源不同版本区间时，必须返回 `divergence` 并阻断自动择一。

**不变量 5.2.2**：`coverage` 字段必须声明语料边界。查询落在边界外 → 返回明确的覆盖缺口，**不得**返回最近似结果。

### 5.3 检索

三层召回，结果必须标注命中层：`alias 精确` / `结构化字段` / `语义`。语义层**不得**单独支撑一个 `source_ids` 引用——引用必须能追到具体条目 id。

---

## 第 6 章 契约与版本

| 契约 | 所有者 | 消费者 |
|---|---|---|
| `contracts/public-api.yaml` | Java | Vue、外部集成 |
| `contracts/internal-engine-api.yaml` | Java + Engine | Engine |
| `contracts/schemas/*.schema.json` | T3 + Engine | 导入器、规则引擎 |
| `web/src/api-types.ts` | 公开契约快照 | Vue |

**不变量 6.1**：`api-types.ts` 必须与 OpenAPI 改动**同一次提交**更新。
**不变量 6.2**：`schemaVersion` 只增不改。`document.parse.v1` 一旦发布，字段语义冻结；变更开 `.v2`。
**不变量 6.3**：Engine 内部结构**不得**出现在公开契约。

---

## 第 7 章 能力门闩

**不变量 7.1**：每个未会签能力必须有**独立命名的**门闩，返回**独立的错误码**。**不得**用一个总开关。

**不变量 7.2**：门闩必须**两侧对齐**。仅开 Java 侧导致任务建成后在 Engine 被标 `failed`，这是**缺陷**，不是可接受降级。理想态：Java 在派发前校验 Engine 能力声明，不一致时直接返 `501`，不建任务。

**不变量 7.3**：门闩解锁的唯一依据是**会签记录 + 验收用例通过**，不是「代码写好了」。

---

## 第 8 章 明确不做

1. 浏览器直连 Engine / MinIO / PostgreSQL / Redis / 向量库
2. 以模型输出直接充当定性结论、量刑数值或法源引用
3. 未经法学会签的量刑比例、界分规则或字段映射投入产出
4. 任何界面把 `baseline_asserted` / `candidate` / `conflicted` 渲染为已审核结论
5. 教学改编案例的结果冒充真实裁判或系统计算
6. 跨 `kind` 求和金额，或对存在 `component_of` 关系的金额重复相加
7. 覆盖范围外罪名的近似替代输出
8. 合规风险评分 / 分级 / 打分
9. 静默使用「最新版」法律，或自行择一解决新旧法冲突
10. 自动通过任何结论（无 `human_review_required: false` 的路径）

---

## 附录 A 与现有实现的差距

| 章节 | 理想态 | 需要做的 |
|---|---|---|
| 3.2 / 3.3 | 规则引擎产出结论 | **全新**。现为无条件 `501` 且无 flag |
| 3.4 | 可解释推算 | **内核已存在**（`calculate_sentencing` 算术分支）；需要真实规则数据与 `calculation_mode` 显式化 |
| 3.5 | 服务端 DOCX 渲染 | **全新**。现 draft body 为 opaque string |
| 3.7 | 统一 `ReviewTarget` | 重构。现为三套机制 + SQL `CASE` 派生 |
| 2.2 | 删除多 key 容错层 | 需先冻结 T3 schema |
| 3.3 | 九罪名覆盖 | 现 4 条；需补 191 / 287 之一 / 303 / 177 之一 / 285 / 286 |
| 5.2 | 时效比对引擎 | **雏形已存在**（双版本掩隐解释 + `as_of_date`）；需升格为独立能力 |
| 5.3 | 三层检索 | `retrieval/` 在树里未接入 |
| 7.2 | 门闩两侧对齐 | 现为已知缺陷 |
