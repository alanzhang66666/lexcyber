# LexCyber 系统架构设计书 v1.3 — PostgreSQL Physical Model

> 读者：T1 / T2 / T3 工程团队、法学负责人、架构评审人员
>
> 文档定位：本文件描述 LexCyber 的**目标架构（Target Architecture）**，用于约束系统实现、接口设计、数据模型、运行时行为与架构评审。
>
> 本文不记录交付状态、日期、feature flag 开关或当前实现完成度。实施状态应由独立 roadmap / delivery 文档维护。
>
> 本文中出现的「必须 / 不得」均表示架构不变量；任何实现若与其冲突，应调整实现，而非默认为修改不变量。

---

# Part I — WHY：系统目标、边界与架构原则

## 0. 文档说明

### 0.1 文档目的

本文用于回答以下问题：

1. LexCyber 解决什么问题，系统边界在哪里；
2. 哪些架构约束不可被局部实现绕过；
3. 各组件分别拥有什么职责与数据；
4. 案件事实、规则、法源、计算结果与复核如何形成可审计版本链；
5. 运行时任务如何创建、执行、失败、重试、复核与归档；
6. AI / LLM 在系统中允许承担什么职责，以及禁止承担什么职责；
7. 安全、可靠性、可观测性、部署与非功能目标如何约束实现。

### 0.2 非目标

本文不描述：

- 当前版本完成度；
- 团队排期；
- feature flag 状态；
- 临时兼容代码；
- 迁移执行顺序；
- 开发任务拆分。

上述内容应进入独立的《架构演进计划 / Architecture Roadmap》。

### 0.3 架构规则分级

本文中的约束分为三类：

- **Invariant（不变量）**：除非经过正式架构评审与三方会签，不得违反；
- **Architecture Decision（架构决策）**：当前选定方案，可通过 ADR 正式变更；
- **Implementation Guidance（实现建议）**：推荐实现方式，只要不违反前两类即可替换。

> 本文原有“必须 / 不得”条款默认均属于 Invariant。

---

## 1. 系统定位与边界

LexCyber 是一个**可审计的刑事研判工作台**，覆盖范围为：**帮助信息网络犯罪活动罪及其邻近罪、上下游罪名及其相关程序性研判能力**。

系统产出的是：

- 带证据的候选结论；
- 带版本的法源引用；
- 带计算过程的数值结果；
- 带版本快照的复核对象；
- 可追溯的文书草稿。

系统产出必须交由具资格的人审确认。系统**不得**独立产出终局的量刑、责任或犯罪结论。

### 1.1 系统上下文

```text
                    ┌────────────────┐
                    │    办案人员     │
                    └───────┬────────┘
                            │
                            ▼
                   ┌─────────────────┐
                   │    LexCyber     │
                   └───────┬─────────┘
                           │
          ┌────────────────┼──────────────────┐
          ▼                ▼                  ▼
      法源 / 规则库       外部模型服务        文档对象存储
      （版本化）          （受控调用）         （原文 / 产物）
```

### 1.2 系统明确不做

1. 浏览器直连 Engine / MinIO / PostgreSQL / Redis / 向量库；
2. 以模型输出直接充当定性结论、量刑数值或法源引用；
3. 未经法学会签的量刑比例、界分规则或字段映射投入生产结论；
4. 将 `baseline_asserted` / `candidate` / `conflicted` 渲染为已审核结论；
5. 将教学改编案例结果冒充真实裁判或系统计算；
6. 跨 `kind` 求和金额，或对存在 `component_of` 关系的金额重复相加；
7. 对覆盖范围外罪名进行近似替代；
8. 生成合规风险评分 / 分级 / 打分；
9. 静默使用「最新版」法律，或由系统自行解决新旧法冲突；
10. 自动通过任何结论。

---

## 2. 架构原则与系统不变量

### 2.1 失败闭合（Fail-closed）

**INV-EXEC-001**：每一个计算单元的返回必须是三态之一：

```text
calculated | blocked | not_applicable
```

不存在「部分成功」。

统一协议：

```text
ComputationResult<T> =
    Calculated<T>
  | Blocked
  | NotApplicable
```

其中：

```text
Calculated<T> {
  status: "calculated",
  value: T,
  human_review_required: true
}

Blocked {
  status: "blocked",
  blockers: [{ code, path, message, retryable }]
}

NotApplicable {
  status: "not_applicable",
  reason,
  evidence_ids
}
```

`path` 必须是可定位到输入字段的 JSON 路径，例如：

```text
rule.adjustments[2].source_ids
```

前端据此高亮字段，不做字符串匹配。

**INV-EXEC-002**：任何 `calculated` 结果必须携带 `human_review_required: true`。系统不存在自动通过路径。

**INV-EXEC-003**：输入不合格时不得降级产出。宁可 `blocked`，不可给一个标注为「仅供参考」的数值或结论。

### 2.2 可解释性

**INV-EXPLAIN-001**：任何数值结论必须附 `steps[]`，每步含：

```text
before → delta → after
```

并附 `source_ids[]`。

**INV-EXPLAIN-002**：任何定性结论必须同时附：

```text
supporting_evidence_ids[]
contrary_evidence_ids[]
```

`contrary_evidence_ids` 可以为空数组，但字段不得缺省。

**INV-EXPLAIN-003**：`source_ids` 必须指向带版本的法源条目，不得仅存法条名称字符串。

### 2.3 法源时效

**INV-LEGAL-001**：每条法源必须具有：

```text
source_version
effective_from
effective_to
```

现行版本的 `effective_to = null`。

**INV-LEGAL-002**：一切检索与规则选取必须显式传入 `as_of_date`。不得存在隐式“用最新版”的调用路径。

**INV-LEGAL-003**：当行为时法与裁判时法产生不同结论时，系统必须并列输出两条路径，并设置：

```text
blocker: law_version_divergence
```

由人审选择。系统不得自行择一。

> 新旧掩饰、隐瞒犯罪所得解释的版本切换，是该机制的首个实例。

### 2.4 数据分类

**INV-DATA-001 金额口径不可互换。**

每个金额必须有 `kind`，各类分开存储、分开展示、禁止跨类求和。

| kind | 说明 |
|---|---|
| `payment_settlement_amount` | 支付结算金额 |
| `illegal_gain` | 违法所得 |
| `crime_amount` | 上游犯罪金额 / 被害人损失 |
| `business_revenue` | 经营性收入，不入罪量评价 |
| `recovery` | 追缴数额 |
| `fine` | 罚金 |

金额实体必须支持：

```text
component_of
```

用以表达组成关系并避免重复相加。

**INV-DATA-002 核验状态必须是五态：**

```text
candidate | baseline_asserted | confirmed | rejected | conflicted
```

`baseline_asserted` 不得渲染为已审核结论；`conflicted` 必须同时展示双方证据，不得折叠。

### 2.5 审计与版本

**INV-VERSION-001**：复核绑定一个不可变结果版本。批准仅确认该版本，不得通过“批准”动作恢复或重跑执行。

**INV-VERSION-002**：重试必须创建新执行；旧结果、审计记录和决定全部保留。

**INV-VERSION-003**：被复核对象的新版本发布时，旧版本上 pending / approved 的复核自动 `superseded`，不得静默继承批准。

**INV-VERSION-004**：确认即锁。

- `facts` confirm 后再 `PUT` → `409`；
- module confirmed 后再 `PUT` → `409 MODULE_CONFIRMED`；
- 解锁必须产生显式新版本，不允许原地修改。

### 2.6 安全边界

| 规则 | 内容 |
|---|---|
| 浏览器 | 只访问 Nginx 暴露的 `/v1` |
| 内部调用 | Java → Engine 必须带 `X-Service-Token` |
| 对象键 | 客户端不得发送 `storageKey`；服务端从属主材料覆写 |
| schema 所有权 | `app` 归 Java，`engine` 归 Python；不得跨 schema 直读 |
| 模型访问 | 只有 `ModelGateway` 可以调用外部模型 API |
| 队列 | Redis 只承载执行号；结果与复核状态持久在 PostgreSQL |
| 迁移 | 只走 Flyway，前向唯一；不得修改已发布迁移 |

### 2.7 幂等与并发

**INV-IDEMP-001**：一切创建型写入必须接受 `Idempotency-Key`，服务端持久绑定请求内容与返回资源。同一身份重放返回同一资源。

**INV-CONCURRENCY-001**：执行租约必须带 fencing token。过期 token 不得 claim 或 complete。

---

# Part II — WHAT：领域、数据、版本与规则模型

## 3. 领域架构

```text
Account
 └─ Case ──────────────────────────────────────┐
     ├─ Document
     ├─ Actor
     ├─ Event
     ├─ Evidence
     ├─ Fact
     ├─ Amount
     ├─ FactsHead        （当前 confirmed facts 版本指针）
     ├─ FactsVersion     （不可变事实集合快照）
     ├─ ModuleHead       （模块流定位 / last-confirmed 指针 / stale 状态）
     ├─ CandidatePath
     ├─ JurisdictionConnection
     ├─ MissingItem
     ├─ DraftHead        （文书流定位 / approved 指针 / stale 状态）
     ├─ ReviewRecord
     └─ CaseArchive      （不可变案件归档清单）

LegalSource（全局，非案件级）
     └─ source_version / effective_from / effective_to / authority / aliases

SentencingRule（全局，非案件级）
     └─ rule_version / legal_review_status / base_months / adjustments[] / bounds / source_ids
```

### 3.1 两条版本轴

| | 案件轴 | 规则轴 |
|---|---|---|
| 实体 | Case 下全部 | `LegalSource`、规则、模板 |
| 版本语义 | 案件事实与案件工件变化 | 法律 / 规则 / 模板变化 |
| 会签主体 | 个案办案人 | 法学负责人 |
| 变更影响 | 单案 | 全部引用该版本的案件 |

**INV-DOMAIN-001**：规则轴版本变化不得回溯改写已确认案件结论。已确认结论冻结所引用的 `source_version` / `rule_version` 快照。

**INV-DOMAIN-002**：新的 `FactsVersion` 被确认后，所有依赖旧事实版本的 `ModuleHead` / `DraftHead` 必须保留原 confirmed / approved 指针并置为 stale；不得自动清空、自动重算或覆盖历史结果。

**INV-DOMAIN-003**：案件规则计算不得以“当前若干可变 Fact 行”作为隐式输入。所有规则执行必须显式引用一个不可变、已确认的 `FactsVersion`。

### 3.2 Schema 冻结规则

现阶段若存在同一语义支持多个候选 key 的容错逻辑，则在 schema 正式冻结后必须删除。

**INV-SCHEMA-001**：schema 冻结后，字段名或结构不匹配应直接触发 schema 校验失败并返回 `blocked`，不得静默容错。

---

## 4. 数据架构

### 4.1 数据所有权

```text
PostgreSQL
├─ schema app
│  ├─ case / document / actor / event
│  ├─ fact / amount / evidence / jurisdiction_connection
│  ├─ facts_version / facts_version_item / facts_head
│  ├─ artifact_stream / artifact_version
│  ├─ module_head / draft_head
│  ├─ review_record
│  ├─ case_archive / case_archive_item
│  └─ idempotency / business audit
│
└─ schema engine
   ├─ execution
   ├─ lease / fencing token
   ├─ checkpoint
   ├─ rule execution log
   └─ model call audit
```

**INV-DATA-OWN-001**：Java 拥有业务事实真相以及对外可见的工件版本；Engine 不得直接读取 `app` schema。

**INV-DATA-OWN-002**：Engine 执行所需案件数据必须通过内部契约获得不可变输入快照，而非运行时跨 schema 查询。

**INV-DATA-OWN-003**：Engine 可以保存执行期 checkpoint / audit，但这些记录不得成为公开业务结果的唯一事实源。公开结果必须发布为 `app.artifact_version`。

### 4.2 生命周期持久化模型

目标架构保留八种职责单一的生命周期角色：

```text
FactsVersion    不可变事实集合快照
FactsHead       当前 confirmed facts 指针
Execution       技术执行尝试
ArtifactVersion 不可变业务产物
ModuleHead      模块最后确认指针 + stale 状态
DraftHead       文书最后批准指针 + stale 状态
ReviewRecord    人审决定
CaseArchive     不可变案件归档清单
```

它们不得互相复制职责。

#### 4.2.1 `FactsVersion` / `FactsHead` — 唯一事实基线

`Fact`、`Amount`、`Actor`、`Event`、`Evidence` 等实体用于编辑与核验；真正进入规则执行的是不可变事实集合快照：

```text
FactsVersion {
  facts_version_id,
  case_id,
  version,
  status,                 // draft | confirmed | superseded
  content_hash,
  created_by,
  created_at,
  confirmed_by,
  confirmed_at
}

FactsVersionItem {
  facts_version_id,
  entity_kind,            // fact | amount | actor | event | evidence | jurisdiction_connection
  entity_id,
  entity_version_or_hash
}

FactsHead {
  case_id,
  confirmed_facts_version_id,
  updated_at
}
```

**INV-FACTS-001**：规则执行输入必须显式引用 `FactsHead.confirmed_facts_version_id`；不得在执行时查询“当前 Fact 行”拼接隐式快照。

**INV-FACTS-002**：确认 `FactsVersion` 是原子操作；确认后不可修改。事实修订必须创建新版本。

**INV-FACTS-003**：同一案件任一时刻最多只有一个 `FactsHead.confirmed_facts_version_id` 作为当前事实基线；旧 `FactsVersion` 永久保留。

**INV-FACTS-004**：候选抽取结果不得直接进入 `confirmed` FactsVersion；必须经过人工核验/确认路径。

#### 4.2.2 `Execution` — 技术执行尝试

`Execution` 位于 `engine` schema，只回答：这一次计算尝试运行到哪里、由哪个 worker 持有、技术上是否完成。

```text
Execution {
  execution_id,
  case_id,
  artifact_stream_id,
  input_snapshot_ref,
  state,                 // created | queued | claimed | running | completed | failed
  fencing_token,
  created_at,
  completed_at
}
```

`Execution` 不得保存 confirmed / approved 状态、Review 状态或“当前业务结果”。

#### 4.2.3 `ArtifactStream` / `ArtifactVersion` — 逻辑工件与不可变版本

```text
ArtifactStream {
  artifact_stream_id,
  case_id,
  kind,                  // parse | compliance | conviction | sentencing | draft
  scope_ref,
  latest_version_id,
  next_version
}

ArtifactVersion {
  artifact_version_id,
  artifact_stream_id,
  version,
  schema_version,
  outcome_status,        // calculated | blocked | not_applicable
  payload,
  blockers[],
  dependency_snapshot,
  execution_id,
  created_at
}
```

`ArtifactVersion` 是业务可见结果的唯一版本实体。

**INV-ARTIFACT-001**：`ArtifactVersion` 一经发布不可修改；重新计算、修正或重试只能产生新版本。

**INV-ARTIFACT-002**：`Execution.failed` 不产生 `ArtifactVersion`；一次受控完成必须恰好发布一个 `ArtifactVersion`。

**INV-ARTIFACT-003**：`blocked` 是合法、可审计的业务产物，不得映射为 `Execution.failed`。

#### 4.2.4 `ModuleHead` — 模块指针，不是结果实体

```text
ModuleHead {
  case_id,
  module,                    // compliance | conviction | sentencing
  artifact_stream_id,
  confirmed_version_id,      // 最后一次人工确认版本，stale 时仍保留
  stale,
  stale_reason,              // facts_changed | dependency_changed | newer_version_published | null
  updated_at
}
```

`ArtifactStream.latest_version_id` 回答“最新结果”，`ModuleHead.confirmed_version_id` 回答“最后一次人工确认结果”，`stale` 回答“该确认现在是否仍有效”。

**INV-MODULE-001**：模块正文只存在于 `ArtifactVersion.payload`；不得在 `ModuleHead` 中保存第二份 `content`。

**INV-MODULE-002**：最新结果、最后确认结果、当前有效性三种语义不得合并为单一 status。

**INV-MODULE-003**：新工件版本或依赖变化使确认失效时，必须保留 `confirmed_version_id` 并标记 stale；不得通过置空指针表达失效。

#### 4.2.5 `DraftHead` — 文书批准指针

```text
DraftHead {
  draft_id,
  case_id,
  artifact_stream_id,
  approved_version_id,       // 最后一次批准版本，stale 时仍保留
  stale,
  stale_reason,              // dependency_changed | newer_version_published | template_invalidated | null
  updated_at
}
```

**INV-DRAFT-HEAD-001**：文书当前批准版本不得通过查询 Review 历史临时推导；必须由 `DraftHead.approved_version_id` 显式记录。

**INV-DRAFT-HEAD-002**：新 draft 版本发布时保留旧 `approved_version_id`，同时设置 stale；旧批准历史不得丢失，但该文书不再满足最终归档门闩。

#### 4.2.6 `ReviewRecord` — 对精确工件版本作决定

```text
ReviewRecord {
  review_id,
  artifact_version_id,
  status,                // pending | approved | rejected | superseded
  decision,
  actor,
  comment,
  created_at,
  decided_at
}
```

Review 永远指向 `artifact_version_id`，而不是“模块当前值”、task 或 execution。

**INV-REVIEW-REF-001**：复核对象的持久化外键必须是 `artifact_version_id`。`ReviewTarget` 只允许作为 API/路由层展示 DTO。

#### 4.2.7 `CaseArchive` — 案件最终不可变归档

归档不是 Review 的状态，而是一份案件级不可变 manifest：

```text
CaseArchive {
  archive_id,
  case_id,
  archive_version,
  archive_profile,          // 核心闭环默认：case.full.v1
  facts_version_id,
  manifest_hash,
  created_by,
  created_at
}

CaseArchiveItem {
  archive_id,
  artifact_version_id,
  role                      // parse | compliance | conviction | sentencing | draft | supporting
}
```

`CaseArchive` 不复制正文；它冻结精确的 `FactsVersion` 和 `ArtifactVersion` 引用，并以 `manifest_hash` 固定归档清单。

**INV-ARCHIVE-001**：归档一经创建不可修改。后续补充材料或重新办理必须形成新事实/工件版本，并创建新的 archive version。

**INV-ARCHIVE-002**：`ReviewRecord` 不保存 `archive_status`；复核与归档是两个独立生命周期。

**INV-ARCHIVE-003**：归档项只能引用不可变版本 ID，不得引用 `latest` / `current` 等可漂移指针。

### 4.3 对象存储

MinIO 用于：原始材料、解析过程中需要回读的源文件、服务端渲染后的 DOCX / 其他文书产物。

对象键由服务端生成或从可信属主对象派生，客户端不得控制最终 `storageKey`。`ArtifactVersion.payload` 可保存对象引用，但不得由客户端直接提交可信对象键。

### 4.4 Redis

Redis 只承担执行队列 / 调度信号职责，队列消息仅承载 `execution_id`。不得把业务结果、最终状态、当前版本指针或复核状态仅存于 Redis。

### 4.5 事务边界

以下操作必须在 `app` schema 内原子完成：

1. 发布 `ArtifactVersion` + 推进 `ArtifactStream.latest_version_id` + 将对应 Head 标记 stale；
2. 新版本发布时，将旧版本仍为 pending 的 Review 置 `superseded`；已决 Review 保留原决定；
3. 批准模块工件版本 + 更新 `ModuleHead.confirmed_version_id` + 清除 stale；
4. 批准文书版本 + 更新 `DraftHead.approved_version_id` + 清除 stale；
5. 确认 `FactsVersion` + 推进 `FactsHead.confirmed_facts_version_id` + 标记依赖 Head stale；
6. 创建 `CaseArchive` + `CaseArchiveItem` + `manifest_hash`；
7. 持久化幂等键与对应创建资源。

跨 `engine` 与 `app` schema 不要求分布式事务。Engine 计算完成后由 Java 负责以一次 `app` 事务发布业务版本；如果发布失败，Execution 保留可诊断状态，重放发布不得重新执行法律计算。

具体锁粒度、顺序与发布幂等规则见 4.8；物理表与约束见 4.6。


### 4.6 PostgreSQL 物理模型（规范性）

本节把 4.2 的逻辑生命周期模型下沉为 PostgreSQL 物理结构。除明确标为“实现建议”的内容外，本节表间关系、唯一性与事务语义属于目标架构的一部分。

#### 4.6.1 设计原则

1. **正文与指针分离**：不可变正文只存在于 version 表；Head 只保存当前指针与有效性。
2. **版本号在流内唯一**：所有业务版本号都以所属 stream / case 为命名空间，不使用全局连续版本号。
3. **跨 schema 不建业务外键**：`app` 不直接依赖 `engine` 表；`execution_id` 作为外部引用保存，通过内部 API / completion identity 校验。
4. **数据库保证结构不变量，领域服务保证语义不变量**：能用 `PK/FK/UNIQUE/CHECK/NOT NULL` 表达的约束必须落到数据库；“依赖是否仍有效”等跨版本语义在锁定事务中验证。
5. **不可变表默认 insert-only**：`artifact_version`、`case_archive`、`case_archive_item` 发布后不得 UPDATE/DELETE。应用账号权限与审计触发器可作为第二层防线。
6. **不用 PostgreSQL ENUM 固化业务状态**：状态字段使用 `varchar/text + CHECK`，避免前向唯一 Flyway 下 ENUM 演进成本过高。

> 以下 DDL 假定案件主表物理名为 `app.cases(id)`；若现有实现使用其他表名，只替换物理名，不改变本节关系语义。

#### 4.6.2 `app.facts_version`

```sql
CREATE TABLE app.facts_version (
    facts_version_id uuid PRIMARY KEY,
    case_id          uuid NOT NULL REFERENCES app.cases(id),
    version          integer NOT NULL CHECK (version > 0),
    content_hash     text NOT NULL,
    created_by       uuid NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),
    confirmed_by     uuid NULL,
    confirmed_at     timestamptz NULL,

    CONSTRAINT uq_facts_version_case_version
        UNIQUE (case_id, version),
    CONSTRAINT uq_facts_version_case_id
        UNIQUE (case_id, facts_version_id),
    CONSTRAINT ck_facts_version_confirmation_pair
        CHECK ((confirmed_by IS NULL) = (confirmed_at IS NULL))
);
```

物理层不保存 `status=draft|confirmed|superseded` 作为第二事实源：

- `confirmed_at IS NULL` → draft；
- `confirmed_at IS NOT NULL` → 曾被 confirmed；
- 是否为“当前 confirmed”由 `facts_head.confirmed_facts_version_id` 唯一决定；
- “superseded”是读取模型语义，不需要回写旧 version 行。

这避免为了把旧版本从 `confirmed` 改成 `superseded` 而破坏 immutable version 语义。

#### 4.6.3 `app.facts_version_item` / `app.facts_head`

```sql
CREATE TABLE app.facts_version_item (
    facts_version_id       uuid NOT NULL REFERENCES app.facts_version(facts_version_id),
    entity_kind            varchar(32) NOT NULL,
    entity_id              uuid NOT NULL,
    entity_version_or_hash text NOT NULL,
    PRIMARY KEY (facts_version_id, entity_kind, entity_id),
    CONSTRAINT ck_facts_item_kind CHECK (
        entity_kind IN ('fact','amount','actor','event','evidence','jurisdiction_connection')
    )
);

CREATE TABLE app.facts_head (
    case_id                    uuid PRIMARY KEY REFERENCES app.cases(id),
    confirmed_facts_version_id uuid NULL,
    updated_at                 timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT fk_facts_head_same_case
        FOREIGN KEY (case_id, confirmed_facts_version_id)
        REFERENCES app.facts_version(case_id, facts_version_id)
        DEFERRABLE INITIALLY IMMEDIATE
);
```

`facts_head` 是“当前事实基线”的唯一权威指针。任何 API 不得通过 `MAX(version)` 或 `ORDER BY confirmed_at DESC` 推导当前事实版本。

#### 4.6.4 `app.artifact_stream`

```sql
CREATE TABLE app.artifact_stream (
    artifact_stream_id uuid PRIMARY KEY,
    case_id             uuid NOT NULL REFERENCES app.cases(id),
    kind                varchar(32) NOT NULL,
    scope_key           text NOT NULL,
    latest_version_id   uuid NULL,
    next_version        integer NOT NULL DEFAULT 1 CHECK (next_version > 0),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT ck_artifact_stream_kind CHECK (
        kind IN ('parse','compliance','conviction','sentencing','draft')
    ),
    CONSTRAINT uq_artifact_stream_scope UNIQUE (case_id, kind, scope_key),
    CONSTRAINT uq_artifact_stream_pair UNIQUE (artifact_stream_id, case_id)
);
```

`scope_key` 必须由服务端生成规范值：

- parse：`document:{document_id}`；
- compliance / conviction / sentencing：`module:{module}`；
- draft：`draft:{draft_id}`。

客户端不得自行决定 `scope_key`。

#### 4.6.5 `app.artifact_version`

```sql
CREATE TABLE app.artifact_version (
    artifact_version_id uuid PRIMARY KEY,
    artifact_stream_id  uuid NOT NULL REFERENCES app.artifact_stream(artifact_stream_id),
    version             integer NOT NULL CHECK (version > 0),
    schema_version      varchar(128) NOT NULL,
    outcome_status      varchar(32) NOT NULL,
    payload             jsonb NOT NULL,
    blockers            jsonb NOT NULL DEFAULT '[]'::jsonb,
    dependency_snapshot jsonb NOT NULL,
    execution_id        uuid NULL,
    output_hash         text NOT NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT uq_artifact_version_stream_version
        UNIQUE (artifact_stream_id, version),
    CONSTRAINT uq_artifact_version_stream_id
        UNIQUE (artifact_stream_id, artifact_version_id),
    CONSTRAINT ck_artifact_outcome CHECK (
        outcome_status IN ('calculated','blocked','not_applicable')
    ),
    CONSTRAINT ck_artifact_blockers_shape CHECK (
        jsonb_typeof(blockers) = 'array'
    ),
    CONSTRAINT ck_artifact_dependency_shape CHECK (
        jsonb_typeof(dependency_snapshot) = 'object'
    )
);
```

`execution_id` 不声明到 `engine.execution` 的数据库 FK。Java 发布时通过 Engine 内部 API 校验 completion identity，并在 `app.execution_publication` 中建立幂等绑定。

完成 `artifact_version` 建表后，为 stream 增加“latest 必须属于本 stream”的复合 FK：

```sql
ALTER TABLE app.artifact_stream
ADD CONSTRAINT fk_artifact_stream_latest_same_stream
FOREIGN KEY (artifact_stream_id, latest_version_id)
REFERENCES app.artifact_version(artifact_stream_id, artifact_version_id)
DEFERRABLE INITIALLY DEFERRED;
```

#### 4.6.6 依赖关系正规化

`dependency_snapshot` 是审计快照，但 stale 传播和影响分析不得依赖 JSON 字符串扫描。发布 Artifact 时必须同步写入可索引依赖表。

```sql
CREATE TABLE app.artifact_facts_dependency (
    artifact_version_id uuid PRIMARY KEY REFERENCES app.artifact_version(artifact_version_id),
    facts_version_id    uuid NOT NULL REFERENCES app.facts_version(facts_version_id)
);

CREATE TABLE app.artifact_artifact_dependency (
    artifact_version_id            uuid NOT NULL REFERENCES app.artifact_version(artifact_version_id),
    depends_on_artifact_version_id uuid NOT NULL REFERENCES app.artifact_version(artifact_version_id),
    PRIMARY KEY (artifact_version_id, depends_on_artifact_version_id),
    CONSTRAINT ck_artifact_no_self_dependency
        CHECK (artifact_version_id <> depends_on_artifact_version_id)
);

CREATE TABLE app.artifact_external_dependency (
    artifact_version_id uuid NOT NULL REFERENCES app.artifact_version(artifact_version_id),
    dependency_kind     varchar(32) NOT NULL,
    dependency_key      text NOT NULL,
    dependency_version  text NOT NULL,
    PRIMARY KEY (artifact_version_id, dependency_kind, dependency_key, dependency_version),
    CONSTRAINT ck_external_dependency_kind CHECK (
        dependency_kind IN ('rule','legal_source','template')
    )
);
```

**INV-DB-DEP-001**：`dependency_snapshot` 与正规化依赖表必须在发布 Artifact 的同一事务内写入；二者不允许出现一边成功、一边失败。

#### 4.6.7 `app.module_head`

```sql
CREATE TABLE app.module_head (
    case_id              uuid NOT NULL REFERENCES app.cases(id),
    module               varchar(32) NOT NULL,
    artifact_stream_id   uuid NOT NULL REFERENCES app.artifact_stream(artifact_stream_id),
    confirmed_version_id uuid NULL,
    stale                boolean NOT NULL DEFAULT true,
    stale_reason         varchar(64) NULL,
    updated_at           timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (case_id, module),
    CONSTRAINT uq_module_head_stream UNIQUE (artifact_stream_id),
    CONSTRAINT ck_module_head_module CHECK (
        module IN ('compliance','conviction','sentencing')
    ),
    CONSTRAINT ck_module_head_stale_reason CHECK (
        stale_reason IS NULL OR stale_reason IN (
            'facts_changed','dependency_changed','newer_version_published',
            'rule_invalidated','legal_source_invalidated'
        )
    ),
    CONSTRAINT ck_module_head_stale_consistency CHECK (
        stale = true OR stale_reason IS NULL
    ),
    CONSTRAINT fk_module_head_stream_same_case
        FOREIGN KEY (artifact_stream_id, case_id)
        REFERENCES app.artifact_stream(artifact_stream_id, case_id),
    CONSTRAINT fk_module_head_confirmed_same_stream
        FOREIGN KEY (artifact_stream_id, confirmed_version_id)
        REFERENCES app.artifact_version(artifact_stream_id, artifact_version_id)
        DEFERRABLE INITIALLY IMMEDIATE
);
```

领域服务创建 `ModuleHead` 时还必须验证：stream 的 `case_id` 与 `module` 对应的 `scope_key` 一致。该约束跨表达形式，不能只靠普通 FK 表达。

#### 4.6.8 `app.draft_head`

```sql
CREATE TABLE app.draft_head (
    draft_id            uuid PRIMARY KEY,
    case_id             uuid NOT NULL REFERENCES app.cases(id),
    artifact_stream_id  uuid NOT NULL UNIQUE REFERENCES app.artifact_stream(artifact_stream_id),
    approved_version_id uuid NULL,
    stale               boolean NOT NULL DEFAULT true,
    stale_reason        varchar(64) NULL,
    updated_at          timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT ck_draft_head_stale_reason CHECK (
        stale_reason IS NULL OR stale_reason IN (
            'dependency_changed','newer_version_published','template_invalidated',
            'facts_changed','module_changed'
        )
    ),
    CONSTRAINT ck_draft_head_stale_consistency CHECK (
        stale = true OR stale_reason IS NULL
    ),
    CONSTRAINT fk_draft_head_stream_same_case
        FOREIGN KEY (artifact_stream_id, case_id)
        REFERENCES app.artifact_stream(artifact_stream_id, case_id),
    CONSTRAINT fk_draft_head_approved_same_stream
        FOREIGN KEY (artifact_stream_id, approved_version_id)
        REFERENCES app.artifact_version(artifact_stream_id, artifact_version_id)
        DEFERRABLE INITIALLY IMMEDIATE
);
```

#### 4.6.9 `app.review_record`

```sql
CREATE TABLE app.review_record (
    review_id           uuid PRIMARY KEY,
    artifact_version_id uuid NOT NULL REFERENCES app.artifact_version(artifact_version_id),
    status              varchar(32) NOT NULL,
    decision            varchar(64) NULL,
    actor_id            uuid NOT NULL,
    comment             text NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    decided_at          timestamptz NULL,

    CONSTRAINT ck_review_status CHECK (
        status IN ('pending','approved','rejected','superseded')
    ),
    CONSTRAINT ck_review_decision_time CHECK (
        (status = 'pending' AND decided_at IS NULL)
        OR
        (status <> 'pending' AND decided_at IS NOT NULL)
    )
);
```

是否允许同一个 `artifact_version_id` 同时存在多个 reviewer / 会签记录，取决于最终会签策略；当前架构**不增加“每版本只能一条 Review”唯一约束**，避免在会签规则未冻结前错误固化数据库模型。

但至少增加查询索引：

```sql
CREATE INDEX ix_review_artifact_status
ON app.review_record(artifact_version_id, status, created_at DESC);
```

#### 4.6.10 `app.execution_publication` — 跨 schema 发布幂等桥

```sql
CREATE TABLE app.execution_publication (
    execution_id        uuid PRIMARY KEY,
    artifact_version_id uuid NOT NULL UNIQUE REFERENCES app.artifact_version(artifact_version_id),
    completion_identity text NOT NULL,
    output_hash         text NOT NULL,
    published_at        timestamptz NOT NULL DEFAULT now()
);
```

它不拥有 Execution 状态，只回答：**某个 completed execution 是否已经被发布成哪个业务 ArtifactVersion**。

**INV-DB-PUB-001**：同一个 `execution_id` 最多发布一个 `artifact_version_id`。

**INV-DB-PUB-002**：重复发布请求若 `completion_identity + output_hash` 相同，返回既有 `artifact_version_id`；若相同 execution 带来不同输出哈希，必须阻断并记录审计异常。

#### 4.6.11 `app.case_archive` / `app.case_archive_item`

```sql
CREATE TABLE app.case_archive (
    archive_id       uuid PRIMARY KEY,
    case_id          uuid NOT NULL REFERENCES app.cases(id),
    archive_version  integer NOT NULL CHECK (archive_version > 0),
    archive_profile  varchar(128) NOT NULL,
    facts_version_id uuid NOT NULL REFERENCES app.facts_version(facts_version_id),
    manifest_hash    text NOT NULL,
    created_by       uuid NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT uq_case_archive_version UNIQUE (case_id, archive_version),
    CONSTRAINT uq_case_archive_manifest UNIQUE (case_id, manifest_hash),
    CONSTRAINT fk_case_archive_facts_same_case
        FOREIGN KEY (case_id, facts_version_id)
        REFERENCES app.facts_version(case_id, facts_version_id)
);

CREATE TABLE app.case_archive_item (
    archive_id          uuid NOT NULL REFERENCES app.case_archive(archive_id),
    artifact_version_id uuid NOT NULL REFERENCES app.artifact_version(artifact_version_id),
    role                varchar(32) NOT NULL,
    PRIMARY KEY (archive_id, artifact_version_id, role),
    CONSTRAINT ck_archive_item_role CHECK (
        role IN ('parse','compliance','conviction','sentencing','draft','supporting')
    )
);
```

`case_archive` 和 `case_archive_item` 均为 insert-only。删除案件时若存在保留义务，删除策略必须由数据保留政策单独定义；本架构不使用 `ON DELETE CASCADE` 自动抹除归档链。

创建 `CaseArchiveItem` 时领域服务必须验证每个 `artifact_version_id` 所属 `ArtifactStream.case_id = CaseArchive.case_id`；普通 FK 无法跨 `artifact_version → artifact_stream → case_archive` 三表表达这一语义，因此该检查必须位于归档事务内，并由集成测试覆盖。

#### 4.6.12 `engine.execution`

```sql
CREATE TABLE engine.execution (
    execution_id        uuid PRIMARY KEY,
    case_id             uuid NOT NULL,
    artifact_stream_id  uuid NOT NULL,
    input_snapshot_ref  text NOT NULL,
    state               varchar(32) NOT NULL,
    fencing_token       bigint NOT NULL DEFAULT 0,
    lease_owner         text NULL,
    lease_expires_at    timestamptz NULL,
    completion_identity text NULL,
    output_hash         text NULL,
    output_envelope     jsonb NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    claimed_at          timestamptz NULL,
    completed_at        timestamptz NULL,

    CONSTRAINT ck_execution_state CHECK (
        state IN ('created','queued','claimed','running','completed','failed')
    ),
    CONSTRAINT ck_execution_completion CHECK (
        (state = 'completed' AND completion_identity IS NOT NULL AND output_hash IS NOT NULL AND output_envelope IS NOT NULL)
        OR state <> 'completed'
    )
);
```

这里的 `case_id / artifact_stream_id` 是不可解释为 FK 的 opaque business references；Engine 不通过它们跨 schema 读取业务表。

### 4.7 索引与查询路径

至少需要以下索引：

```sql
CREATE INDEX ix_artifact_version_stream_created
ON app.artifact_version(artifact_stream_id, created_at DESC);

CREATE INDEX ix_artifact_facts_dependency_facts
ON app.artifact_facts_dependency(facts_version_id, artifact_version_id);

CREATE INDEX ix_artifact_dependency_upstream
ON app.artifact_artifact_dependency(depends_on_artifact_version_id, artifact_version_id);

CREATE INDEX ix_artifact_external_dependency_lookup
ON app.artifact_external_dependency(dependency_kind, dependency_key, dependency_version);

CREATE INDEX ix_module_head_case_stale
ON app.module_head(case_id, stale);

CREATE INDEX ix_draft_head_case_stale
ON app.draft_head(case_id, stale);

CREATE INDEX ix_archive_case_created
ON app.case_archive(case_id, archive_version DESC);
```

核心读取路径必须做到无需扫描 payload：

- 当前事实：`facts_head → facts_version`；
- 模块最新结果：`module_head.artifact_stream_id → artifact_stream.latest_version_id`；
- 模块最后确认：`module_head.confirmed_version_id`；
- 文书最后批准：`draft_head.approved_version_id`；
- 影响分析：依赖表反向索引；
- 归档重现：`case_archive → case_archive_item → artifact_version`。

### 4.8 事务、锁与并发规则

目标默认隔离级别为 PostgreSQL `READ COMMITTED`，通过**显式行锁 + 唯一约束**控制聚合内并发；不要求全局使用 `SERIALIZABLE`。

锁必须按照稳定顺序获取，避免不同服务方法形成反向锁序：

```text
Case / aggregate root
→ FactsHead
→ ArtifactStream
→ ModuleHead / DraftHead
→ ReviewRecord
```

只有实际需要的行才加锁。

#### 4.8.1 确认 FactsVersion

事务步骤：

```text
1. SELECT facts_head ... FOR UPDATE
2. 校验目标 FactsVersion 属于同案且尚未 confirmed
3. UPDATE facts_version SET confirmed_by/confirmed_at
4. UPDATE facts_head SET confirmed_facts_version_id = target
5. 通过 artifact_facts_dependency 找出依赖旧 facts 的 ArtifactVersion
6. 将对应 ModuleHead / DraftHead 标记 stale，保留 confirmed/approved 指针
7. COMMIT
```

若两个操作者同时确认不同 FactsVersion，同一个 `facts_head` 行锁保证只有一个事务先推进当前事实指针；后提交者必须重新读取并决定是冲突 `409` 还是基于新 head 重新发起确认，不得静默覆盖。

#### 4.8.2 发布 ArtifactVersion

```text
1. 读取 Engine completed outcome；得到 execution_id / completion_identity / output_hash
2. BEGIN
3. 查询 execution_publication(execution_id)
   - 已存在且 hash 相同 → 直接返回既有 artifact_version_id
   - 已存在且 hash 不同 → 阻断
4. SELECT artifact_stream ... FOR UPDATE
5. version = artifact_stream.next_version
6. INSERT artifact_version
7. INSERT dependency rows
8. UPDATE artifact_stream
      SET latest_version_id = new_version,
          next_version = next_version + 1
9. 对 module/draft stream：Head 保留旧 confirmed/approved 指针并置 stale
10. 将该 stream 旧版本上仍 pending 的 Review 置 superseded
11. INSERT execution_publication
12. COMMIT
```

`next_version` 只在这个锁定事务中推进，因此并发发布不会产生重复 version，也不会使用 `MAX(version)+1`。

#### 4.8.3 批准模块 ArtifactVersion

```text
1. BEGIN
2. SELECT module_head ... FOR UPDATE
3. SELECT artifact_stream ... FOR SHARE
4. 校验 artifact_version 属于该 stream
5. 校验 artifact_version 仍是可批准版本：
   - 不是 blocked
   - Review 未 superseded
   - dependency snapshot 仍有效
   - 若策略要求“只允许批准 latest”，则必须等于 latest_version_id
6. 写入/完成 ReviewRecord
7. UPDATE module_head
      SET confirmed_version_id = artifact_version_id,
          stale = false,
          stale_reason = null
8. COMMIT
```

“是否只能批准 latest”作为默认规则采用 **是**。若未来需要批准历史版本，必须另开 ADR，因为它会改变 `latest / confirmed / stale` 的基本语义。

#### 4.8.4 批准 Draft

与模块批准同构，只是推进：

```text
DraftHead.approved_version_id
```

批准前必须重新校验 Facts / Module / Template 依赖仍有效；不能仅相信生成时的 gate。

#### 4.8.5 stale 传播

stale 传播必须基于正规化依赖关系，而不是“模块顺序猜测”。

当上游 ArtifactVersion 被新确认版本替代时，可以通过反向依赖查找直接消费者；如存在多级依赖，使用递归 CTE 或领域服务逐层传播：

```sql
WITH RECURSIVE affected(artifact_version_id) AS (
    SELECT aad.artifact_version_id
    FROM app.artifact_artifact_dependency aad
    WHERE aad.depends_on_artifact_version_id = :old_version

    UNION

    SELECT aad.artifact_version_id
    FROM app.artifact_artifact_dependency aad
    JOIN affected a
      ON aad.depends_on_artifact_version_id = a.artifact_version_id
)
SELECT artifact_version_id FROM affected;
```

传播最终只修改 Head 的有效性，不修改历史 ArtifactVersion。

#### 4.8.6 创建 CaseArchive

```text
1. BEGIN
2. SELECT app.cases ... FOR UPDATE       // 作为同案归档版本分配锁
3. SELECT facts_head ... FOR SHARE
4. SELECT required module_head / draft_head ... FOR SHARE
5. 逐项执行 effective-confirmed / effective-approved 检查
6. 固化精确 facts_version_id 与 artifact_version_id 清单
7. canonicalize manifest → 计算 manifest_hash
8. archive_version = 当前同案最大版本 + 1（受 case 行锁保护）
9. INSERT case_archive
10. INSERT case_archive_item...
11. COMMIT
```

归档事务从第 3 步起使用的 Head 必须保持锁定直到 manifest 落库，避免检查通过后、写 archive 前依赖被并发推进。

### 4.9 幂等键物理模型

所有创建型公开写入必须支持持久幂等：

```sql
CREATE TABLE app.idempotency_record (
    principal_id       uuid NOT NULL,
    idempotency_key    varchar(200) NOT NULL,
    request_hash       text NOT NULL,
    resource_type      varchar(64) NOT NULL,
    resource_id        uuid NOT NULL,
    response_status    integer NOT NULL,
    created_at         timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (principal_id, idempotency_key)
);
```

同一 `(principal_id, idempotency_key)`：

- request hash 相同 → 返回同一资源；
- request hash 不同 → `409 IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST`。

幂等记录必须与目标资源创建处于同一 `app` 事务。

### 4.10 数据库不可变性与权限

建议将表按写入模型区分权限：

**Insert-only / immutable after publish**：

- `artifact_version`；
- `artifact_*_dependency`；
- `case_archive`；
- `case_archive_item`；
- confirmed 后的 `facts_version` payload / item 集合。

**允许受控 UPDATE**：

- `facts_head`；
- `artifact_stream`；
- `module_head`；
- `draft_head`；
- `review_record`；
- `engine.execution`。

数据库角色不应给业务运行账号对 immutable 表的任意 `DELETE` 权限。若当前部署无法做到细粒度角色，至少通过 repository 层禁止 UPDATE/DELETE，并以审计触发器检测违规操作。

### 4.11 物理模型中的单一事实源

| 问题 | 唯一权威位置 |
|---|---|
| 当前事实版本 | `facts_head.confirmed_facts_version_id` |
| 最新 Artifact | `artifact_stream.latest_version_id` |
| Artifact 下一版本号 | `artifact_stream.next_version` |
| 模块最后确认版本 | `module_head.confirmed_version_id` |
| 模块确认当前是否有效 | `module_head.stale` + dependency validation |
| Draft 最后批准版本 | `draft_head.approved_version_id` |
| Draft 批准当前是否有效 | `draft_head.stale` + dependency validation |
| Execution 是否已发布 | `execution_publication` |
| 某版本的人审历史 | `review_record.artifact_version_id` |
| 案件某次最终冻结内容 | `case_archive` + `case_archive_item` |

**INV-DB-SOURCE-001**：任何 API / SQL 不得通过“扫描历史后猜当前值”的方式替代上述 Head / binding 表。

---

---

## 5. 统一案件生命周期

### 5.1 端到端唯一主链

```text
Document
   │
   ▼
Parse ArtifactVersion
   │
   ▼
Candidate Extraction / Human Verification
   │
   ▼
FactsVersion (confirmed)
   │
   ▼
Compliance ArtifactVersion ──review──► ModuleHead(compliance) valid
   │
   ▼
Conviction ArtifactVersion ──review──► ModuleHead(conviction) valid
   │
   ▼
Sentencing ArtifactVersion ──review──► ModuleHead(sentencing) valid
   │
   ▼
Draft ArtifactVersion ───────review──► DraftHead approved + valid
   │
   ▼
CaseArchive
```

每个箭头必须能回答：输入版本、输出版本、触发者、失败语义、人审对象、失效条件和追溯路径。

### 5.2 四类状态严格分离

```text
Execution.state
= created | queued | claimed | running | completed | failed

ArtifactVersion.outcome_status
= calculated | blocked | not_applicable

ReviewRecord.status
= pending | approved | rejected | superseded

Head validity
= stale=false
| stale=true + stale_reason
```

技术执行、业务结果、人审决定、当前有效性不得共用同一个 status 字段。

### 5.3 事实形成闭环

```text
Document
  ↓ parse execution
Parse ArtifactVersion
  ↓ candidate extraction
candidate Fact / Amount / Actor / Event / Evidence
  ↓ human verify / edit / reject
FactsVersion draft
  ↓ confirm
FactsVersion confirmed
  ↓
FactsHead.confirmed_facts_version_id
```

确认事实版本时，必须验证参与规则计算的必需实体满足其核验约束；不满足则阻止确认，而不是生成“部分 confirmed”的事实版本。

**INV-FACTS-005**：一个 `FactsVersion` 要么整体 confirmed，要么不是 confirmed；规则执行不得接收混合不同事实版本的“当前行集合”。

### 5.4 Artifact 版本号与 Execution 解耦

```text
ArtifactStream(conviction@case-123)
  ├─ v1 ← execution e1
  ├─ v2 ← execution e2
  └─ v3 ← execution e4

execution e3 = failed
```

**INV-VERSION-005**：业务版本号只在成功发布 `ArtifactVersion` 时递增；技术失败不得制造空版本。

### 5.5 依赖快照

每个 `ArtifactVersion` 必须记录实际使用版本：

```text
dependency_snapshot {
  facts_version_id,
  dependency_artifact_version_ids[],
  rule_versions[],
  legal_source_versions[],
  template_version?,
  execution_id,
  input_hash
}
```

不得存“当前版本”引用代替实际版本 ID。

### 5.6 新工件版本发布：保留最后确认，标记 stale

```text
1. insert artifact_version(vN)
2. artifact_stream.latest_version_id = vN
3. old pending review -> superseded
4. 已决 review 保留原决定
5. module stream → ModuleHead.stale = true; stale_reason = newer_version_published
6. draft stream  → DraftHead.stale = true; stale_reason = newer_version_published
```

不得清空 `confirmed_version_id` / `approved_version_id`。两者回答“最后一次人工确认/批准是哪一版”；`stale` 回答“它现在是否还能作为当前有效依据”。

### 5.7 依赖变化：统一 stale 传播

新的 `FactsVersion` 被确认时：

```text
FactsHead.confirmed_facts_version_id = facts_vN
  ├─ dependent ModuleHead.stale = true
  │    stale_reason = facts_changed
  └─ dependent DraftHead.stale = true
       stale_reason = dependency_changed
```

上游模块重新确认新版本后，所有直接依赖该模块旧版本的下游 Head 必须置 stale：

```text
compliance changed  → conviction / sentencing / draft（按实际 dependency snapshot）
conviction changed  → sentencing / draft
sentencing changed  → draft
```

传播必须基于实际 `dependency_snapshot`，不得只靠固定模块名猜依赖。

### 5.8 人审确认与批准

Module artifact：

```text
Review approved
  + artifact is latest
  + dependencies still current
  + outcome_status in {calculated, not_applicable}
      ↓
ModuleHead.confirmed_version_id = artifact_version_id
ModuleHead.stale = false
ModuleHead.stale_reason = null
```

Draft artifact：

```text
Review approved
  + artifact is latest
  + dependencies still current
  + template legal_review_status = approved
  + outcome_status = calculated
      ↓
DraftHead.approved_version_id = artifact_version_id
DraftHead.stale = false
DraftHead.stale_reason = null
```

`blocked` 工件允许查看、评论和保留历史，但不得成为 confirmed / approved 指针。

### 5.9 Effective confirmation / approval 的唯一判定

```text
is_effectively_confirmed(module_head) =
  module_head.confirmed_version_id != null
  && module_head.stale == false

is_effectively_approved(draft_head) =
  draft_head.approved_version_id != null
  && draft_head.stale == false
```

下游 Controller、SQL、Engine adapter 不得自行复制该逻辑。

### 5.10 重试语义

```text
retry != reuse execution

retry = new Execution
      → [completed] new ArtifactVersion
      → [failed]    no ArtifactVersion
```

旧 execution / artifact / review / head history 全部保留。

### 5.11 归档闭环

归档由 Java 在门闩满足后显式创建，不派发 Engine：

```text
ArchiveRequest
   ↓ validate archive profile
FactsVersion current + confirmed
Required ModuleHeads effective-confirmed
DraftHead effective-approved
No selected artifact outcome = blocked
   ↓
CaseArchive + CaseArchiveItems + manifest_hash
```

核心归档 profile `case.full.v1` 至少冻结：

- 当前 `FactsVersion`；
- 适用的 compliance confirmed artifact；
- conviction confirmed artifact；
- sentencing confirmed artifact；
- approved draft artifact；
- 上述 artifact 依赖链中引用的 parse / supporting artifact。

若 compliance 为 `not_applicable`，归档冻结该已确认的 `not_applicable` artifact，而不是省略该阶段。

**INV-ARCHIVE-004**：归档成功后，清单中的任何版本不得被替换；后续变化只能创建新的 archive version。

**INV-ARCHIVE-005**：归档不是“锁死整个 Case 不允许继续工作”。是否允许归档后继续追加材料属于产品/合规策略；架构上只能通过新版本 + 新 archive version 表达，不允许修改既有 archive。

### 5.12 ReviewTarget 的最终定位

```text
ReviewTargetView {
  artifact_version_id,
  kind,
  case_id,
  module?,
  document_id?,
  draft_id?,
  version,
  return_route
}
```

唯一权威复核定位键仍是 `artifact_version_id`。

---

## 6. 法源与规则架构

### 6.1 法源实体

```text
LegalSource {
  id,
  title,
  document_number,
  article,
  jurisdiction,
  authority,
  source_version,
  effective_from,
  effective_to,
  official_url,
  excerpt,
  aliases: [...],
  superseded_by: [...],
  supersedes: [...]
}
```

**INV-LEGAL-004**：`authority` 决定冲突时的优先级，不得仅以 `effective_from` 的新旧顺序替代权威层级判断。

**INV-LEGAL-005**：`supersedes` / `superseded_by` 必须显式建链，该关系是数据，不是注释。

### 6.2 时效比对引擎

```text
resolve(query, as_of_date, conduct_date, judgment_date)
  → {
      conduct_law: [...],
      judgment_law: [...],
      divergence: [...]
    }
```

**INV-LEGAL-006**：当 `conduct_date` 与 `judgment_date` 落在同一法源不同版本区间时，必须返回 `divergence` 并阻断系统自动择一。

**INV-LEGAL-007**：`coverage` 必须声明语料边界。查询落在边界外时必须返回明确覆盖缺口，不得返回近似结果。

### 6.3 检索

三层召回：

1. alias 精确；
2. 结构化字段；
3. 语义召回。

结果必须标注命中层。

语义召回不得单独支撑一个 `source_ids` 引用；最终引用必须追溯到具体 `LegalSource.id`。

### 6.4 统一规则模型

规则层是 Engine 内独立子系统。规则版本与代码版本解耦。

```text
RulePackage {
  rule_id,
  rule_version,
  family,
  legal_review_status,
  effective_from,
  effective_to,
  source_ids,
  predicate,
  outcome,
  required_evidence_kinds
}
```

规则 family 至少包括：

```text
compliance
conviction
distinction
sentencing
```

**INV-RULE-001**：规则更新不得要求应用代码发版。

**INV-RULE-002**：任何参与产出结论的规则版本必须处于 `approved`。

---

# Part III — HOW：服务、运行时、流水线、契约与 AI

## 7. 总体服务架构

### 7.1 Container Architecture

```text
Browser
  │ 只访问 /v1
  ▼
Nginx ──┬─→ Web（Vue 静态资源）
        └─→ Java Public API
              ├─→ PostgreSQL / schema app
              ├─→ MinIO
              └─→ Engine Internal API（X-Service-Token）
                        │
                        ├─→ Redis / Dramatiq（只传 execution_id）
                        ├─→ PostgreSQL / schema engine
                        ├─→ MinIO
                        └─→ ModelGateway → 外部模型 API
```

### 7.2 职责划分

| 层 | 拥有 | 明确不拥有 |
|---|---|---|
| Java | 公开契约、鉴权与属主、案件/材料/事实、任务生命周期、结果版本、复核、业务审计、对象写入边界 | 法律规则判断 |
| Engine | 执行租约、checkpoint、解析、规则引擎、模板渲染、模型调用、Engine 审计 | 公开契约、鉴权、属主判定 |
| 规则层 | 合规 / 定罪 / 界分 / 量刑规则、法源语料、模板字段字典 | 案件业务数据 |

**INV-SVC-001**：Java 不得内嵌法律判断。能力门闩只做能力与前置条件检查，不做法律推理。

---

## 8. 运行时架构

### 8.1 两套状态机必须分离

#### Execution 技术状态

```text
created
  ↓
queued
  ↓
claimed
  ↓
running
  ├─→ completed
  └─→ failed
```

`completed` 只表示 Engine 已形成一个受控结果，可进入业务版本发布。

#### ArtifactVersion 业务结果状态

```text
calculated | blocked | not_applicable
```

**INV-RUNTIME-001**：`calculated / blocked / not_applicable` 不得作为 `Execution.state`；`failed` 也不得作为 `ArtifactVersion.outcome_status`。技术状态与业务语义必须正交。

### 8.2 典型执行序列

```text
Browser
   │ POST /cases/{id}/modules/{module}/executions
   ▼
Java API
   │ validate ownership
   │ validate gate
   │ resolve/create ArtifactStream
   │ snapshot inputs + dependencies
   │ create Execution
   │ enqueue execution_id
   ▼
Redis
   │
   ▼
Engine Worker
   │ claim(execution_id, fencing_token)
   │ load immutable snapshot
   │ resolve rules + legal sources
   │ calculate
   │ persist engine audit/checkpoint
   │ mark Execution completed + return outcome envelope
   ▼
Java API
   │ validate outcome schema
   │ transaction:
   │   publish ArtifactVersion
   │   move latest_version_id
   │   supersede prior active reviews
   │   clear module confirmed pointer if applicable
   ▼
Browser
```

这里的“Engine completed”和“ArtifactVersion 已发布”是两个事件。它们之间不使用跨 schema 分布式事务。

### 8.3 Engine 返回协议

Engine 返回的不是 `ResultVersion`，而是待发布的结果 envelope：

```text
ExecutionOutcome<T> =
  | { status: "calculated", value: T, human_review_required: true }
  | { status: "blocked", blockers: [...] }
  | { status: "not_applicable", reason, evidence_ids: [...] }
```

Java 校验该 envelope 与目标 `schema_version` 后，发布成 `ArtifactVersion`。

### 8.4 Lease 与 fencing

Engine worker 必须通过租约 claim 执行。

过期 worker 即使恢复运行，也不得：

- 更新 checkpoint；
- 将 Execution 标记为 completed；
- 返回可发布结果。

Java 发布 `ArtifactVersion` 时还必须校验对应 Execution 的最终 fencing token / completion identity，防止 stale worker 的结果被发布。

### 8.5 Checkpoint

Checkpoint 用于长执行的技术恢复，但不得成为业务版本。

Checkpoint 恢复属于同一个 Execution 的技术实现；只有显式 retry 才创建新 Execution。

具体 checkpoint 粒度：**TBD — 需要基于解析 / 渲染 / 模型调用步骤进一步定义。**

### 8.6 发布幂等

`Execution completed → ArtifactVersion publish` 必须可幂等重放。

建议唯一约束：

```text
artifact_version.execution_id UNIQUE
```

同一 completed Execution 被重复消费时只能返回已经发布的同一个 `artifact_version_id`，不得产生 vN / vN+1 两个版本。

---

## 9. 端到端业务流水线

### 9.1 总览

```text
材料 → 解析 → 候选抽取 → FactsVersion确认 ─→ ① 合规 ─→ ② 定罪 ─→ ③ 量刑 ─→ ④ 文书
                                                   │        │        │        │
                                                   └────────┴────────┴────────┘
                                                         任一工件均可独立复核
                                                                           │
                                                                           ▼
                                                                    ⑤ 案件归档
```

**INV-PIPE-001**：③ 量刑要求②定罪 effective-confirmed；②要求当前 `FactsVersion` confirmed；④要求其实际依赖的上游模块 effective-confirmed；⑤归档要求归档 profile 中所有必需 Head 有效。门闩不得跳过，违反返回 `409`。

**INV-PIPE-002**：①合规可以 `not_applicable`；此时不是阻断，而是形成一个可复核、可确认、可归档的 `not_applicable` artifact，且必须带理由与证据。

### 9.2 材料解析 → 候选 → FactsVersion

| 项 | 设计 |
|---|---|
| 输入 | Document 原文 |
| 计算归属 | Engine parse / extraction；人工核验由 Java 业务流承载 |
| 产出 | `parse` ArtifactVersion + candidate entities + `FactsVersion` |
| 门闩 | candidate 不得直接 confirmed；FactsVersion 确认必须通过完整性校验 |
| 失败语义 | parse 技术异常 → Execution failed；可解释输入缺失 → blocked parse artifact |
| 人审 | FactsVersion confirmation；parse artifact 可独立复核但不代替事实确认 |

`FactsVersion` 是所有下游规则的唯一事实基线。

### 9.3 ① 合规筛查

| 项 | 设计 |
|---|---|
| 输入 | confirmed FactsVersion 中的 facts、events、evidence、actors、amounts |
| 计算归属 | Engine `ComplianceRuleEngine` |
| 产出 | `case.compliance.v2` |
| 版本依赖 | facts version + rule version + legal source version |
| 门闩 | 无 confirmed FactsVersion → `409 FACTS_NOT_CONFIRMED`；规则未 approved → `blocked` |
| 失败语义 | 受控输入问题 → `blocked`；技术异常 → `failed` |
| 人审 | `artifact_version_id`（compliance stream） |

```text
ComplianceRule {
  rule_id,
  rule_version,
  legal_review_status: approved,
  source_ids: [...],
  dimension,
  predicate,
  outcome_status,
  required_evidence_kinds: [...]
}
```

**INV-COMP-001**：`checklist[].status` 是客观状态，不得是风险评分或分级。

### 9.4 ② 定罪研判

| 项 | 设计 |
|---|---|
| 输入 | confirmed FactsVersion、subjective_knowledge、amounts、jurisdiction_connections、①（若适用） |
| 计算归属 | Engine `ConvictionRuleEngine` |
| 产出 | `case.conviction.v2` |
| 版本依赖 | facts + compliance + rule + legal source versions |
| 门闩 | FactsVersion 未 confirmed → `409`；①适用但未 effective-confirmed → `409`；无核实管辖连接点 → `blocked` |
| 人审 | `artifact_version_id`（conviction stream） |

```text
CandidatePath {
  actor_id,
  label,
  baseline_position,
  supporting_evidence_ids: [...],
  contrary_evidence_ids: [...],
  legal_source_ids: [...],
  exclusion_reason
}
```

**INV-CONV-001**：必须产出多路径。单一路径输出视为缺陷。

**INV-CONV-002**：排除路径必须保留，并带排除理由与相反证据。

**INV-CONV-003**：罪名界分规则必须独立可寻址，不能仅作为某条路径的文字附注。

**INV-CONV-004**：主观明知不得由金额单独推定；存在相反证据时状态为 `conflicted`。

**INV-CONV-005**：语料未覆盖的罪名不得输出为候选路径，必须返回 `missing_item: charge_out_of_coverage` 并列明请求罪名。

目标罪名覆盖：

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

### 9.5 ③ 量刑分析

| 项 | 设计 |
|---|---|
| 输入 | effective-confirmed conviction selected path、confirmed FactsVersion 中 amounts / 量刑情节、`as_of_date` |
| 计算归属 | Engine `SentencingRuleEngine` |
| 产出 | `sentencing.result.v2` |
| 版本依赖 | conviction + facts + rule + legal source versions |
| 门闩 | conviction 未 effective-confirmed → `409`；规则/调节项未 approved → `blocked`；参数未 confirmed 或无 evidence → `blocked` |
| 人审 | mandatory；复核键为 `artifact_version_id` |

输出至少包括：

```text
term_months
term_range_months
fine
recovery_cny
steps[]
rule_version
source_ids
input_snapshot
calculation_mode
```

`calculation_mode`：

| mode | 语义 | 可否展示为系统结论 |
|---|---|---|
| `explainable_calculation` | 起点 + 调节比例推算 | 可，但必须带完整 `steps[]` |
| `reviewed_disposition_replay` | 重放法学已审阅宣告刑 | 可，须标注“已审阅建议” |
| `dual_track` | 两者并列 | 可，差异必须触发复核 |

**INV-SENT-001**：`calculation_mode` 不得缺省。

**INV-SENT-002**：调节运算符封闭集为 `fixed_months | percent_of_base | percent_of_current`；未知运算符 → `blocked: operation_unsupported`。

**INV-SENT-003**：`percent_of_current` 依赖顺序，因此 `adjustments[]` 顺序属于规则内容，必须随 `rule_version` 冻结。

**INV-SENT-004**：`minimum_months` / `maximum_months` 夹逼必须来自法定刑幅度并绑定法源；夹逼时必须在 `steps[]` 留痕。

### 9.6 ④ 文书生成

| 项 | 设计 |
|---|---|
| 输入 | 当前 confirmed FactsVersion + 实际需要的 effective-confirmed 模块结果 + `DocumentTemplate` |
| 计算归属 | Engine `DocumentRenderer` |
| 产出 | `draft.v2` ArtifactVersion |
| 版本依赖 | facts + dependency artifact versions + template version |
| 人审 | `artifact_version_id`；批准后推进 `DraftHead.approved_version_id` |

```text
DocumentTemplate {
  template_id,
  template_version,
  legal_review_status,
  source_object_key,
  fields: [{ name, required, source_binding, type }],
  branches: [{ condition, fields }],
  placeholder_syntax: "【…】"
}
```

**INV-DRAFT-001**：未替换占位符必须服务端阻断。正文存在任何 `【…】` → `blocked: unresolved_placeholder`。

**INV-DRAFT-002**：必填字段缺失或条件分支未选定 → `blocked`，不得填默认值或空串。

**INV-DRAFT-003**：`fieldValues` 只能来自 confirmed 案件数据；引用 candidate / conflicted / baseline_asserted → `blocked: field_source_unconfirmed`。

**INV-DRAFT-004**：模板未 approved 时允许渲染预览，但不得批准；预览产物必须有不可去除水印。

### 9.7 横切复核

复核不是管道末端，而是所有 ArtifactVersion 的横切能力：

```text
ReviewRecord {
  review_id,
  artifact_version_id,
  status,
  decision,
  actor,
  comment,
  created_at,
  decided_at
}
```

**INV-REVIEW-001**：Review 只绑定 `ArtifactVersion`。

**INV-REVIEW-002**：复核批准不得触发执行、重算或恢复任务；只产生人审决定，并在满足条件时推进相应 Head 指针。

**INV-REVIEW-003**：`returnTarget` 不作为业务主键持久化；前端导航由 `ArtifactVersion → ArtifactStream.scope_ref` 解析。

### 9.8 ⑤ 案件归档

| 项 | 设计 |
|---|---|
| 输入 | `archive_profile` + 当前有效版本集合 |
| 计算归属 | Java |
| 产出 | immutable `CaseArchive` |
| 门闩 | 当前 FactsVersion confirmed；profile 必需 ModuleHead effective-confirmed；DraftHead effective-approved；被选 artifact 不得 blocked |
| 失败语义 | 条件未满足 → `409 ARCHIVE_PRECONDITION_FAILED` + 可定位缺口 |

归档不修改 ReviewRecord，也不移动历史结果；它只创建不可变 manifest。

### 9.9 阶段到统一模型映射

| 阶段 | 持久化模型 | scope | Head / pointer | 复核定位 |
|---|---|---|---|---|
| 材料解析 | `ArtifactStream.kind=parse` | document | 无 | `artifact_version_id` |
| 事实确认 | `FactsVersion` | case | `FactsHead` | Facts confirmation |
| ① 合规 | `ArtifactStream.kind=compliance` | case + module | `ModuleHead` | `artifact_version_id` |
| ② 定罪 | `ArtifactStream.kind=conviction` | case + module | `ModuleHead` | `artifact_version_id` |
| ③ 量刑 | `ArtifactStream.kind=sentencing` | case + module | `ModuleHead` | `artifact_version_id` |
| ④ 文书 | `ArtifactStream.kind=draft` | draft | `DraftHead` | `artifact_version_id` |
| ⑤ 归档 | `CaseArchive` | case | archive version | 不适用 |

所有可计算工件共享：

```text
Execution → ArtifactVersion → ReviewRecord
```

事实使用 `FactsHead`，三个业务模块使用 `ModuleHead`，文书使用 `DraftHead`；这些 Head 都只保存稳定指针和有效性，不保存正文。

### 9.10 门闩统一读取

下游模块只能通过 Java 领域服务读取依赖状态：

```text
FactsBaselineService.requireConfirmed(case_id)
ModuleConfirmationService.requireEffectiveConfirmation(case_id, module)
DraftApprovalService.requireEffectiveApproval(draft_id)
ArchiveEligibilityService.evaluate(case_id, archive_profile)
```

**INV-PIPE-003**：Controller / SQL / Engine adapter 不得自行重新推导“facts 是否 confirmed”“module 是否有效确认”“draft 是否有效批准”“case 是否可归档”。

---

## 10. AI / Model Architecture

规则引擎负责产出结论；模型只允许用于：

1. 从解析正文中抽取候选事实 / 主体 / 事件 / 金额，统一落 `candidate`；
2. 对规则引擎已经确定的结论生成叙述文本；
3. 辅助语义检索召回。

```text
                    ┌─ Candidate Extraction
                    │
Engine ─ ModelGateway ─ Narrative Generation
                    │
                    └─ Retrieval Assistance
```

模型禁止直接：

```text
Model
  ╳ → candidate_paths
  ╳ → checklist[].status
  ╳ → term_months
  ╳ → source_ids
```

**INV-AI-001**：模型输出不得直接成为法律结论、量刑结果或法源引用。

**INV-AI-002**：模型叙述与规则结论必须分字段存储，并在 UI 中可视区分。

**INV-AI-003**：每次模型调用必须留审计：

```text
provider
model
model_version
purpose
prompt_version
input_hash
output_hash
execution_id
```

其中 `purpose / prompt_version` 为本版架构新增的建议字段；具体 schema 需后续会签。

---

## 11. API 与契约

| 契约 | 所有者 | 消费者 |
|---|---|---|
| `contracts/public-api.yaml` | Java | Vue、外部集成 |
| `contracts/internal-engine-api.yaml` | Java + Engine | Engine |
| `contracts/schemas/*.schema.json` | T3 + Engine | 导入器、规则引擎 |
| `web/src/api-types.ts` | 公开契约快照 | Vue |

**INV-CONTRACT-001**：`api-types.ts` 必须与 OpenAPI 改动在同一次提交更新。

**INV-CONTRACT-002**：`schemaVersion` 只增不改；已发布 schema 的字段语义冻结，变更必须发布新版本。

**INV-CONTRACT-003**：Engine 内部结构不得出现在公开契约。

### 11.1 生命周期 API 形状

```text
POST /cases/{caseId}/facts-versions
POST /cases/{caseId}/facts-versions/{factsVersionId}/confirm
GET  /cases/{caseId}/facts-head

POST /cases/{caseId}/modules/{module}/executions
GET  /executions/{executionId}

GET  /artifact-versions/{artifactVersionId}
GET  /cases/{caseId}/modules/{module}

POST /artifact-versions/{artifactVersionId}/reviews
GET  /artifact-versions/{artifactVersionId}/reviews

GET  /drafts/{draftId}

POST /cases/{caseId}/archives
GET  /cases/{caseId}/archives/{archiveId}
```

语义：

- Facts API 创建并确认不可变 `FactsVersion`，确认后推进 `FactsHead`；
- `POST .../executions` 只创建技术执行尝试并返回 `execution_id`；
- `GET /executions/...` 只回答技术状态及完成后关联的 `artifact_version_id`；
- `GET /artifact-versions/...` 返回不可变业务结果；
- module 查询返回 latest / last-confirmed / stale 指针，不复制结果正文；
- draft 查询返回 latest / approved / stale 指针；
- Review API 只接受 `artifact_version_id`；
- Archive API 显式创建不可变 manifest，不通过修改 ReviewRecord 完成归档。

解析与文书可以有面向业务的创建入口，但最终同样映射到 `Execution → ArtifactVersion`，不得另造 task result 版本体系。

**INV-API-LIFE-001**：公开 API 中 `taskId` 不得同时承担执行 ID、结果 ID、复核目标 ID 三种语义。

### 11.2 错误语义

建议统一分层：

```text
4xx  → 请求 / 状态门闩 / 属主问题
501  → 能力未开放或两侧能力声明不一致
blocked → 合法执行后的业务阻断结果
5xx  → 技术失败
```

具体错误码表：**TBD — 建议拆为附录并作为契约的一部分。**

---

## 12. 能力门闩

**INV-GATE-001**：每个未会签能力必须有独立命名门闩并返回独立错误码，不得使用一个总开关。

**INV-GATE-002**：门闩必须 Java / Engine 两侧对齐。Java 在派发前必须校验 Engine 能力声明；不一致时直接返回 `501`，不得先创建任务再让 Engine 标 `failed`。

**INV-GATE-003**：能力解锁依据必须是“会签记录 + 验收用例通过”，不得仅以“代码完成”作为开启依据。

---

# Part IV — OPERATE：安全、可靠性、可观测性与部署

## 13. 安全架构

### 13.1 Trust Boundaries

```text
[Browser / External]
        │
        ▼
┌──────────────────────┐
│ Boundary 1: Nginx    │
└─────────┬────────────┘
          ▼
┌──────────────────────┐
│ Boundary 2: Java API │
└─────────┬────────────┘
          ▼
┌──────────────────────┐
│ Boundary 3: Engine   │
└─────────┬────────────┘
          ▼
┌──────────────────────┐
│ Boundary 4: Data     │
│ PG / Redis / MinIO   │
└──────────────────────┘
```

### 13.2 已明确威胁与控制

| 威胁 | 控制 |
|---|---|
| 客户端伪造 object key | 服务端覆写 `storageKey` |
| 非属主探测案件存在性 | 非属主与不存在统一 `404` |
| Browser 绕过公开 API | 网络与反向代理边界阻断 |
| Java 冒充 Engine 调用方 | `X-Service-Token` |
| 过期 worker 覆盖新结果 | fencing token |
| Engine 绕过业务层读案件 | 禁止跨 schema 直读 |
| 任意模块绕过模型网关 | 所有外部模型仅经 `ModelGateway` |
| 静默新旧法切换 | `as_of_date` + divergence blocker |

### 13.3 待补安全设计

以下内容原始材料未提供，需要独立确定：

- 用户认证机制；
- RBAC / ABAC 模型；
- token 生命周期与 rotation；
- 数据静态加密与密钥管理；
- 备份加密；
- 审计日志防篡改策略；
- 敏感数据脱敏策略；
- 模型供应商的数据留存策略。

以上均标记为 **TBD**，不得由本架构文档自行假设。

---

## 14. 可靠性架构

### 14.1 Fail-closed

所有业务计算在输入不完整、规则未批准、证据未确认、版本冲突等情况下必须返回 `blocked`，不得“尽力而为”生成近似业务结论。

### 14.2 技术失败与业务阻断隔离

```text
blocked = 业务输入 / 法律规则层可解释阻断
failed  = 网络 / 数据库 / worker / 模型 / IO 等技术失败
```

二者必须具有不同的 API 表达、监控指标与重试策略。

### 14.3 重试

重试产生新 execution，不覆盖旧 execution / result / review。

技术重试策略（次数、退避、死信）：**TBD**。

### 14.4 灾难恢复

以下目标原始材料未定义：

```text
RPO: TBD
RTO: TBD
Backup Frequency: TBD
Restore Verification: TBD
```

---

## 15. 可观测性

系统至少需要三类观测：

### 15.1 技术日志

用于定位：

- API 请求；
- worker claim；
- queue；
- DB / MinIO / model provider 错误；
- checkpoint 与 lease。

### 15.2 业务审计

必须能追踪：

```text
who
when
case_id
artifact_id
artifact_version
execution_id
rule_version
source_version
action
before_hash
after_hash
```

具体字段集合：**TBD — 需与现有审计表对齐。**

### 15.3 Metrics

至少区分：

- `calculated` / `blocked` / `not_applicable` 数量；
- `failed` 数量；
- blocker code 分布；
- execution duration；
- queue latency；
- review pending duration；
- model call latency / error；
- rule / source version 使用分布。

### 15.4 Trace

建议以 `execution_id` 作为跨 Java / Engine / Worker / ModelGateway 的核心关联键。

是否采用 OpenTelemetry：**Architecture Decision TBD**。

---

## 16. 部署架构

当前材料只足以确定逻辑组件，不足以确定生产拓扑。

### 16.1 逻辑部署单元

```text
Nginx
Web static
Java API
Engine API / Worker
PostgreSQL
Redis
MinIO
External Model Provider
```

### 16.2 待确认部署项

以下内容必须在生产架构评审中补齐：

- 单机 / VM / Kubernetes / 容器平台；
- Java 与 Engine 副本数；
- Worker 水平扩缩容策略；
- PostgreSQL 高可用；
- Redis 高可用；
- MinIO 冗余与对象生命周期；
- 网络分区与 firewall；
- dev / staging / prod 隔离；
- secrets 管理；
- migration 执行职责。

全部标记为 **TBD**。

---

## 17. 非功能目标（NFR）

原始架构材料未给出性能和容量基线，因此本章仅定义需要明确的指标，不填写猜测值。

| 类别 | 指标 | 目标 |
|---|---|---|
| Availability | Public API SLO | TBD |
| Latency | Case read P95 | TBD |
| Latency | Task creation P95 | TBD |
| Execution | Rule execution P95 | TBD |
| Execution | Document parse P95 | TBD |
| Capacity | Max document size | TBD |
| Capacity | Max documents per case | TBD |
| Capacity | Concurrent executions | TBD |
| Recovery | PostgreSQL RPO | TBD |
| Recovery | PostgreSQL RTO | TBD |
| Review | Max pending review age | TBD |

这些数值应来源于产品目标、合规要求和性能基线，而不是由架构文档自行推定。

---

## 18. 架构决策记录（ADR）

### ADR-LIFE-001 — 生命周期对象收敛

**Decision**：使用 `Execution → ArtifactVersion → ReviewRecord` 作为唯一通用生命周期链；模块额外使用 `ModuleHead` 保存 confirmed/stale 指针。

**Consequences**：

- 删除独立 `ResultVersion` 实体，统一为 `ArtifactVersion`；
- `ReviewTarget` 降级为 View DTO，不再持久化多态目标；
- `ModuleState` 收敛为不含正文的 `ModuleHead`；
- `Execution.state` 与业务三态分离；
- task 不再作为结果或复核的领域抽象，仅可保留为兼容 API / UI 概念。

### ADR-LIFE-002 — 端到端案件闭环

**Decision**：引入 `FactsVersion/FactsHead`、`DraftHead` 与 `CaseArchive`，把生命周期从“计算结果闭环”扩展为“材料 → 事实 → 模块 → 文书 → 归档”的案件闭环。

**Consequences**：

- 规则执行只接受 confirmed `FactsVersion`；
- 新事实或新工件不清空旧确认/批准指针，而是把对应 Head 标记 stale；
- Draft 批准状态由 `DraftHead.approved_version_id` 显式表达；
- Review 与 Archive 解耦，删除 `ReviewRecord.archive_status`；
- `CaseArchive` 冻结精确版本 manifest，可产生后续 archive version，但不可修改旧 archive；
- stale 传播基于实际 dependency snapshot。

### ADR-LIFE-003 — 生命周期物理模型与并发边界

**Decision**：生命周期闭环在 PostgreSQL 中采用“immutable version + mutable head + normalized dependency + publication binding”四类结构；聚合内并发使用 `READ COMMITTED + SELECT ... FOR UPDATE/SHARE + UNIQUE/FK/CHECK`，不依赖全局 `SERIALIZABLE`。

**Consequences**：

- `FactsVersion` 的当前性只由 `FactsHead` 表达，物理层不再维护冗余 `superseded` 状态；
- `ArtifactVersion` 与依赖关系同事务发布，stale 传播使用正规化依赖表，不扫描 JSON payload；
- `ArtifactStream.next_version` 在行锁下分配业务版本号；
- `Execution` 与 `ArtifactVersion` 通过 `execution_publication` 做跨 schema 幂等绑定，不建立跨 ownership 外键；
- Archive 创建锁定同案 Head，检查与 manifest 固化处于同一事务；
- 数据库结构约束优先由 PK/FK/UNIQUE/CHECK 保证，跨版本有效性由领域服务在锁定事务内验证。

建议将以下关键决策拆为 ADR：

1. ADR-001 — Java / Engine 职责边界；
2. ADR-002 — `app` / `engine` schema ownership；
3. ADR-003 — Redis 仅传 execution id；
4. ADR-004 — fail-closed 三态计算协议；
5. ADR-005 — 规则与代码版本解耦；
6. ADR-006 — Reviewable Artifact / immutable result version；
7. ADR-007 — ModelGateway 单一外部模型出口；
8. ADR-008 — 法源双时点解析与 divergence blocker；
9. ADR-009 — 服务端文书渲染；
10. ADR-010 — capability gate 双侧声明。

ADR 模板建议：

```text
Context
Decision
Consequences
Alternatives Considered
Migration / Compatibility Notes
```

---

## 19. 架构验收标准

系统进入某一架构能力的“已实现”状态前，至少应满足：

1. 契约已固定并有版本；
2. 规则 / 法源 / 模板处于相应 approved 状态；
3. 架构不变量对应自动化测试已存在；
4. blocked / failed 路径均有测试；
5. 结果可以追溯到输入版本、规则版本、法源版本；
6. review 绑定不可变版本；
7. 重试不会覆盖旧 execution / result；
8. 关键审计字段可追踪；
9. Java / Engine capability gate 一致；
10. 对越权、伪造 storageKey、stale fencing token 等边界行为有验收用例；
11. 下游规则执行可证明只读取单一 confirmed `FactsVersion`；
12. 新 facts / 新 artifact 发布后，旧确认指针保留但 effective confirmation 自动失效；
13. Draft 批准版本可直接通过 `DraftHead` 查询，不依赖 Review 历史推导；
14. 归档前置条件失败时返回可定位缺口，归档成功后 manifest 不可变；
15. 从任一 `CaseArchive` 可追溯到 FactsVersion、核心 ArtifactVersion、对应 ReviewRecord、规则版本与法源版本。
16. 两个并发 Artifact 发布请求不会产生重复 stream version，且 `next_version` 不出现竞态；
17. 同一 completed Execution 重放发布只得到同一个 `artifact_version_id`，不同 output hash 会被阻断；
18. Facts / Module / Draft 的 current 指针均通过 Head 直接读取，不依赖扫描历史推导；
19. stale 传播可以通过正规化 dependency 表完成，核心流程不依赖解析 `dependency_snapshot` JSON；
20. 归档事务在并发事实/模块更新下不能生成“检查时有效、落库时已失效”的混合 manifest；
21. 数据库自动化测试覆盖 PK/FK/UNIQUE/CHECK、幂等冲突、并发版本分配与 immutable table 禁止修改。

---

# 附录 A — 核心对象摘要

## A.1 Amount

```text
Amount {
  id,
  kind,
  value,
  component_of,
  verification_status,
  evidence_ids
}
```

## A.2 CandidatePath

```text
CandidatePath {
  actor_id,
  label,
  baseline_position,
  supporting_evidence_ids,
  contrary_evidence_ids,
  legal_source_ids,
  exclusion_reason
}
```

## A.3 生命周期核心对象

```text
FactsVersion {
  facts_version_id, case_id, version, status, content_hash, confirmed_by, confirmed_at
}

FactsHead {
  case_id, confirmed_facts_version_id
}

Execution {
  execution_id, artifact_stream_id, input_snapshot_ref, state, fencing_token
}

ArtifactStream {
  artifact_stream_id, case_id, kind, scope_ref, latest_version_id, next_version
}

ArtifactVersion {
  artifact_version_id, artifact_stream_id, version, schema_version,
  outcome_status, payload, blockers, dependency_snapshot, execution_id
}

ModuleHead {
  case_id, module, artifact_stream_id, confirmed_version_id, stale, stale_reason
}

DraftHead {
  draft_id, case_id, artifact_stream_id, approved_version_id, stale, stale_reason
}

ReviewRecord {
  review_id, artifact_version_id, status, decision, actor, comment
}

CaseArchive {
  archive_id, case_id, archive_version, archive_profile, facts_version_id, manifest_hash
}

CaseArchiveItem {
  archive_id, artifact_version_id, role
}
```

`ReviewTargetView` 仅为 API 展示 / 导航 DTO，权威定位键为 `artifact_version_id`。

## A.4 LegalSource

```text
LegalSource {
  id,
  title,
  document_number,
  article,
  jurisdiction,
  authority,
  source_version,
  effective_from,
  effective_to,
  official_url,
  excerpt,
  aliases,
  superseded_by,
  supersedes
}
```

---

# 附录 B — 待补架构事项（不等同实施 backlog）

以下事项是“设计信息尚未确定”，不是当前交付状态：

- Authentication / Authorization 模型；
- 审计日志防篡改方案；
- secrets / key management；
- deployment topology；
- HA / DR；
- RPO / RTO；
- 性能与容量目标；
- checkpoint 粒度；
- execution 技术重试策略；
- 完整错误码目录；
- `case.full.v1` archive profile 的业务必需项是否需要按案件类型细分；
- 归档后是否允许继续追加材料的产品/合规策略；
- 统一审计事件 schema；
- ModelGateway prompt version schema；
- OpenTelemetry 是否采用。

这些项目应在对应架构评审后转化为确定的 Architecture Decision 或 Invariant。

---

# 附录 C — 架构主线

LexCyber 的核心架构可以概括为：

```text
Document
   ↓
Parse Artifact
   ↓
Candidate Data
   ↓ Human confirmation
FactsVersion
   ↓
Deterministic Rules + Versioned Legal Sources
   ↓
ArtifactVersion
   ↓ Human Review
Confirmed / Approved Head
   ↓
CaseArchive
```

系统追求的不是“永远只有一个当前结论”，而是：

```text
immutable history
+ explicit current pointers
+ explicit staleness
+ human decisions bound to exact versions
+ reproducible archive manifests
```

由此形成完整闭环：

```text
材料可追溯 → 事实可冻结 → 计算可重现 → 结论可复核 → 失效可解释 → 文书可批准 → 案件可归档
```
