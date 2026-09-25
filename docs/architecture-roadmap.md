# LexCyber 架构演进 Roadmap（v1.3 实施）

> 本文件承载 v1.3 §0.2 明确排除出架构书的「交付状态 / 阶段 / 进度」内容。
> 目标架构唯一权威：`LexCyber-system-architecture-v1.3-postgresql-physical-model.md`。
> 矛盾裁决：`docs/adr/ADR-0001` ~ `ADR-0006`。

## 基线

- 冻结点 tag：`arch-v13-baseline`（main `a078dea`）
- `competition_submission/`、`本科生组+…/`：冻结快照，不再与主树同步
- `/v1` 契约：冻结为读取兼容层；新生命周期端点走 `/v2`

## 阶段状态

| 阶段 | 内容 | 状态 |
|---|---|---|
| 0 | 决策收口 + 基线冻结 | ✅ 完成：ADR-0001..0006、tag `arch-v13-baseline`、roadmap、文档指针 |
| 1 | 主键迁移到 uuid（V13 + legacy_id_map） | ✅ 代码完成，**未编译验证**（本机无 JDK/Docker）。V13 + IdentityService + 全部服务 `?::uuid` 绑定 + 契约 format:uuid + 导入 checkpoint epoch（`lexcyber.import-checkpoint.v2-uuid`） |
| 2a | 五张实体表（actor/event/evidence/amount/jurisdiction_connection） | ✅ 代码完成，未验证。V14 建表 + 从 `metadata_json.relations` 抽取；amount kind 封闭集落 CHECK，不可归类标 `conflicted`（ADR-0003） |
| 2b | FactsVersion/FactsHead + FactsBaselineService | ✅ 代码完成，未验证。V14 + FactsBaselineService（`next_version` 锁内分配）+ FactService 降为 /v1 适配层 |
| 3 | ArtifactStream/ArtifactVersion + 依赖表 + execution_publication + 三套结果合并 | ✅ 代码完成，未验证。V15 + ArtifactPublicationService（§4.8.2 十二步）+ 回填经 `artifact_backfill_map` + EngineResultService 改走发布路径 |
| 4 | ModuleHead/DraftHead + 有效确认判定 + stale 传播 | ✅ 代码完成，未验证。V16 + ModuleConfirmationService/DraftApprovalService/StalePropagationService（递归 CTE 反索引）；ModuleStateService 降为适配层；`ModulePolicies.MODULES` 纳入 sentencing |
| 5 | ReviewRecord 改绑 artifact_version_id + CaseArchive | ✅ 代码完成，未验证。V17（不可改绑历史行审计后删除）+ V18 + CaseArchiveService（锁内评估 + manifest_hash）+ ReviewService 重写；`/v1` review archive 端点返 410 |
| 6 | engine.execution 契约分离 + fencing + outcome envelope | ✅ 代码完成，未验证。engine/V5 + store.py fencing（claim 铸 token，checkpoint/stage/complete 全部带 token 门控）+ `waiting_review`/`timed_out` 移出执行态 + Java `taskStatusOf` 映射 `output_envelope.human_review_required` |
| 7 | 统一幂等 + `/v2` 契约 + 前端迁移 + 删多 key 容错层 | 🔶 部分完成：V19 + IdempotencyService + `contracts/public-api-v2.yaml`（18 paths）+ V2LifecycleController/Service + `api-types.ts` v2 类型。前端已迁：CaseFactsPanel（facts-entities + 版本 CAS 确认）、useCaseModule（moduleHead + artifactVersion + dispatch + openReview，覆盖定罪/合规页 + 运行分析入口）、AnalysisPage（/v2 量刑派发 + 定罪工件金额）、ReviewDetailPage（模块内容走工件）、DocumentsPage（模板渲染区块）。`apiV2` 客户端 + 契约测试已加；文档/任务轮询/复核队列保留 /v1 兼容读层。未做：`module-content.ts` 多 key 容错层**待 payload schema 冻结后删除** |
| 8a | 法源/规则/模板注册与会签（P5 前置基建） | ✅ 代码完成并在真实库验证。engine/V6 注册表（legal_source + alias + supersession 链 + rule_package + template_package + signoff_record）+ `engine/rules/registry.py` + `/internal/v1/capabilities` 等 6 个内部端点 + `EngineCapabilitiesClient`；`/v2` 模块派发已接真实能力门闩（无 approved 规则 → `MODULE_EXECUTION_UNAVAILABLE`，有能力但适配器未实现 → `ENGINE_ADAPTER_PENDING`） |
| 8b | 规则层（合规/定罪/界分执行体） | 🔶 部分完成：`engine/rules/evaluator.py`（谓词 DSL：all/any/not + exists/missing/eq/neq/gt/gte/lt/lte/in/contains/confirmed；facts/amounts/entities 寻址 + confirmed_sum 聚合）+ `engine/adapters/module_analysis.py`（compliance.analyze/conviction.analyze → case.*.v2 payload，缺快照/缺 approved 规则 fail-closed，谓词错误 → blocked，fired 规则绑 source 做双时点解析）；`/v2` 派发已翻成真实建任务（能力门闩→嵌 factsSnapshot→createModuleTask）；`engine/rules/corpus/core_rules.json` 7 条法学底稿（pending 待会签）。未做：文书渲染 |
| 8c | 可解释量刑（注册表化） | 🔶 部分完成：`engine/adapters/sentencing_v2.py`——factsSnapshot 路径走注册表（base_tiers 择档 + when-gated adjustments + 显式夹逼留痕 + ROUND_HALF_UP），产出 sentencing.v2；旧 metadata 重放保留兼容。未做：地方细则插件、缓刑/罚金独立计算块 |
| 8d | 文书渲染 | 🔶 部分完成：`engine/adapters/document_render.py`（`draft.render` → draft.v2；approved 模板 + `{{path}}` 占位符按 evaluator 语义解析 facts/amounts/entities/artifacts；解析失败 → blocked 不产正文）；`registry.active_template` + capabilities 增 draft 模块；Java `POST /v2/cases/{id}/drafts/render`（doc_type 模板门闩 + factsSnapshot + 上游最新 payload 嵌入）+ `GET /v2/cases/{id}/drafts`（渲染结果发现）；流绑定 `draft:{docType}`；DocumentsPage「模板渲染」区块（派发→轮询→展示正文/阻断）。未做：模板语料（仅 1 个测试模板）、下载导出 |
| 9 | 法源层 + AI 边界 + 门闩双侧 + 可观测性 | 🔶 法源注册 + 双时点解析（`resolve_temporal`）已随 8a 落地；新旧链数据、AI 边界审计、可观测性未做 |

## 验证状态（2026-09-24 实测）

**环境已就位**：Docker 29.7.2、`maven:3.9-eclipse-temurin-21`（容器化编译，宿主无 JDK/Maven）、Python 3.13.2、Node 25。

**关键事实**：现有 `postgres_v03` 卷只应用到 app V11 / engine V4（6 案 15 档 24 复核 28 任务）。**V12–V19 与 engine V5 是未发布迁移**——无 checksum 漂移，可按需修改；「已执行迁移前向修复」预案未启用。全量备份：`~/lexcyber-backups/lexcyber-pre-v13-20260924.dump`。

**已验证**：

| 项 | 结果 |
|---|---|
| `mvn compile` + `test-compile` | ✅ 通过（修了 FactService 缺 `Map` import、EngineDispatcherTest 构造器） |
| Flyway V1–V19 存量升级（真实数据副本） | ✅ 通过；首次跑暴露并已修 6 个迁移级缺陷（见下） |
| Flyway V1–V19 全新安装（`lexcyber_test`，lex_app 身份） | ✅ 通过 |
| engine V1–V5 | ✅ 通过 |
| `python -m pytest -q` | ✅ 105 通过 / 1 跳过（修了 4 个 `complete_execution` 新签名 stub 与 `timed_out`→`failed` 断言） |
| `ruff check engine/`、`py_compile` | ✅ 通过 |
| `npm --prefix web run build` | ✅ 通过（早前一轮） |
| Java 单测（TEST_JDBC_URL 外部库路径） | ✅ 84/84 通过（75 旧 + 9 新 FactsBaselineServiceTest） |

**首验发现并修复的缺陷**（全部发生在未发布迁移/未验证代码上，未造成真实损失）：

1. V14：`case_amount` 建表缺 `attributes` 列（INSERT 引用）；`verification_status` varchar(32) 放不下演示数据的 44 字符状态 → 加列 + 放宽 64。
2. V15：DO 块内 `rv` 别名与 DECLARE 变量冲突（两处）；**更严重**：非 parse 任务（13 条 `sentencing.calculate` 执行结果）完全不回填——结果与复核全丢。已改为「模块流 = 执行版本 + 手工正文版本」合并回填，未映射任务类型写审计。
3. V16：回填引用不存在的 `s.module` → `ms.module`。
4. V17：**原逻辑会静默删除 12 条真实复核**（actor 解析失败 + `case_id` NULL → `DELETE WHERE actor_id IS NULL` 无审计）。已修：case_id 由绑定 artifact 回填、actor 解析链扩为 username→artifact 案 owner→task 案 owner、代位写 `review_actor_substituted` 审计、仍失败的审计后删。实测 24/24 保留。
5. V13：`pgcrypto` 未指定 schema，随 Flyway 迁移期 search_path 装进 `app` schema，业务角色运行时找不到 `digest()` → `WITH SCHEMA public` + `ALTER EXTENSION ... SET SCHEMA public`。
6. Java：`queryForList` 对 timestamptz 返回 `Timestamp` 强转 `OffsetDateTime` 崩（FactService 加 `toOffset`）；`stream.findFirst()` 对 NULL 列 NPE（3 处 `flatMap(ofNullable)` → `filter(nonNull)`）；幂等冲突码改回契约冻结的 `IDEMPOTENCY_CONFLICT`；`module_head.stale DEFAULT true` 被 `factsStale` 误读（从未确认≠事实已变，改按 `stale_reason` 非空计）。

**本轮（P1–P4 续）已落地并测试通过的修改**：

1. **FactsVersion 全量快照**：`createDraftVersion` 覆盖六类实体（items + entities 分节），`facts_version_item` 登记全部成员（条目级语义哈希）。
2. **confirm CAS**：`expectedConfirmedFactsVersionId` 入参，锁内比对不一致 → `409 FACTS_HEAD_CONFLICT`（§4.8.1 后到者不得静默覆盖）。
3. **事实闭环端点**：`GET facts-versions`（历史）/ `GET …/{id}`（含 payload）/ `GET …/diff?against=`（added/removed/changed 分节）/ `POST …/clone`（快照回写工作副本，不碰 head 与旧版本）/ `GET|PUT facts-entities[/kind]`（/v2 工作副本读写；确认后仍可编辑，仅影响下一次快照）。契约与 api-types 已同步（INV-CONTRACT-001）。
4. **发布幂等加固**：`execution_publication` 检查抽到 `publishedVersionOrThrow`，stream 行锁内重查——并发双发不再撞唯一索引变 500。
5. **统一锁序审计修复**（原实现存在真实死锁环）：`publish` 按 stream→head→review 加锁，而 confirm/approve/decide 按 head/review→stream 加锁，可互相等待。已将 `ModuleConfirmationService.confirm`、`DraftApprovalService.approve` 改为 stream SHARE → head UPDATE；`ReviewService.decide` 在 review UPDATE 前先取 stream SHARE。全局序：`case → facts_head → stream → head → review → publication`。
6. **派发期绑定**：`TaskService.create/retry` 按 taskType 解析 (kind, scope_key) → `ensureStreamLocked` → `ExecutionRequest.artifactStreamId`；输入快照引用：`document:{id}@sha256:{hash}`（DocumentService metadata 已带 sha256）或 `facts_version:{id}`。有案模块任务缺 confirmed FactsVersion → 409。
7. **V2 契约修复**：`name: x; in: path` 分号写法是非法 YAML，9 处全展开；pyyaml 解析通过（16 paths/14 schemas/8 params）。`FactsBaselineServiceTest` 新增 8 用例覆盖上述验收点。

**本轮（P5/8a 注册表）已落地并实测通过**：

1. **engine/V6 注册表**：`legal_source`（source_key+source_version 唯一、生效区间、authority 封闭集、coverage 边界、content_hash）+ `legal_source_alias` + `legal_source_supersession`（显式新旧链，INV-LEGAL-005）+ `rule_package`（family 封闭集、source_ids 绑定具体版本、required_evidence_kinds）+ `template_package` + `signoff_record`；`lex_engine` 受限角色授权实测通过。
2. **三层触发器防护**：approved/superseded 禁删；approved 内容冻结仅允许 approved→superseded 退役；`approved`/`rejected`/`signed_off`/`disputed`/`unsupported` 评审结论必须走 `signoff()` 同事务路径（`engine.signoff_authorized` GUC，直连 SQL 被拒——实测验证）。
3. **`engine/rules/registry.py`**：`register_*` / `signoff` / `capabilities`（模块可用性 = 所需 family 全有 approved 包）/ `active_rules`（approved-only 产出面，INV-RULE-002）/ `resolve_temporal`（双时点解析：跨版本 → `LAW_VERSION_DIVERGENCE` 阻断自动择一；区间外 → 覆盖缺口不近似，INV-LEGAL-006/007）/ `coverage_check`；`seed.py` 语料播种（10/10 已入册，文种映射保真）。
4. **内部端点**：`/internal/v1/capabilities` + `/internal/v1/registry/{legal-sources,rules,templates,signoffs,resolve}`，全部 `X-Service-Token` 门控；`internal-engine-api.yaml` 已同步。
5. **Java 门闩接通**：`EngineCapabilitiesClient` + `V2LifecycleService.dispatchModuleExecution` 改为真实能力查询。
6. **验证**：`tests/integration/test_rule_registry.py` 8/8 通过（真实 V6 schema：登记/重复拒绝/无 GUC 批准被拒/approved 不可变/会签退役/未知 source 绑定拒绝/双时点 divergence+缺口/模板会签/能力映射）；engine-migrate V5+V6 干净应用 + repair 校验和同步。

**本轮（P10a 全栈端到端）已实测通过**：

1. **五段管道全链路跑通**（compose 全栈，HTTP 驱动）：注册 → 建案 → facts/amounts 实体写入 → FactsVersion 建版 + CAS 确认（v1→v2）→ 定罪/合规/量刑派发 → Engine 消费 approved 规则包执行 → 工件发布（`case.conviction.v2`/`case.compliance.v2`/`sentencing.v2`/`draft.v2`）→ 复核裁决 → `effectivelyConfirmed=true` → `case.full.v1` 归档（manifestHash + 3 工件入册）。
2. **失效传播实测**：facts v2 确认后旧工件 stale；对基于 v1 的合规工件批准被 `DEPENDENCY_STALE` 正确拦截，重跑 v2 后批准通过。
3. **渲染阻断实测**：模板含未解析占位符（`defendant_name` 缺失 / `amounts.inflow.confirmedSum` 非法 kind）→ `blocked` 且不产正文；修正模板 1.0.1 + 补事实后 rendered。
4. **修复三个真实缺陷**：
   - `input_hash` 409 循环——factsSnapshot 里 BigDecimal 保 scale 序列化（`8000.0000`）与 Python `json.dumps`（`8000.0`）canonical 不一致；`TaskService.normalizeJson` 派发前归一化，`TaskServiceHashTest` 覆盖。
   - 模块/文书结果不发布——`EngineResultService` 只认 document 解析任务；新增 `publishModuleArtifact`（kind/scope_key 与派发绑定一致，schema_version/status/依赖快照取自 payload，rules/template/sources → external_dependency，draft 上游模块 → artifact_dependency）。
   - nginx 无 `/v2/` 路由（405）——已补 `nginx.v03.conf`。
5. **注册表清理**：corpus 规则 `settlement`/`inflow` → `payment_settlement_amount`（ADR-0003），两条规则升 1.0.1 并会签，旧版退役；残留 approved 测试规则/模板（`it-*`、旧 `fact:` 谓词、`indictment-draft@1.0.0`）全部退役。
6. **开发库补齐**：app schema V12→V19 由 `lex_migrator` 应用（Java Flyway 用 `lex_app` 无 `pgcrypto` 权限）；V14+ 表补 `lex_app` 授权。

**本轮（P10b 受控演示）进展**：

1. **三案导入完成**：`scripts/import_three_case_demo.py`（demo_runner 账号）——A/B/C 建案 + 文档上传解析 + facts + 模块壳全部 completed=3/failed=0。
2. **语料代差发现**：demo bundle 事实是叙述文本（`type` 作键），金额 kind（`non_crime_flow`/`personal_profit`）在 ADR-0003 封闭集外——不能直接进规则管道。为案例 A 编写了**键化覆盖层**（knowledge_of_crime/help_type/contact_timing 等按 bundle 已审定结论映射，locator 注明 `bundle:*` 出处；28万→`business_revenue`、3万→`illegal_gain`、96万→`crime_amount`，不写 `payment_settlement_amount`——忠实于「非支付结算」的原审定）。
3. **案例 A 全管道实测**：定罪 calculated（构成要件+`illegal_gain≥1万`严重度命中；掩隐界分、诈骗共犯正确不命中）；量刑 9.0→8.1 月（base tier+坦白）；文书渲染因模板需 `payment_settlement_amount` 正确 `blocked`——案例 A 本就不是支付结算型，fail-closed 行为正确。
4. **CAS 并发实测**：错误 expected head → `409 FACTS_HEAD_CONFLICT`。
5. **发现的口径分歧**：bundle 审定基准 12–18 月 vs corpus 量刑规则算出 8.1 月——规则基准档与案载裁量有偏差，属规则语料精度问题，留待法学评审校正。

**仍待办**：案例 B/C 键化覆盖层（需法学审定映射）、`module-content.ts` 多 key 容错层删除（待 payload schema 冻结）、§19 其余并发用例（双发布/归档交错）、真实法学负责人会签（当前 e2e 占位）、文书模板对非支付结算案的占位符策略（可选占位符语法 or 按 doc_type 分模板）。

## 关键不变量速查

- 计算单元三态：`calculated | blocked | not_applicable`，`blocked` 不是 `failed`
- 发布绑定：`execution_publication` 权威 + `artifact_version.execution_id` 部分唯一索引（ADR-0001）
- `FactsVersion` 不存 `status` 列，DTO 派生（ADR-0002）
- 金额 `kind` 封闭 6 类 + `component_of`（ADR-0003）
- 「从未确认」= `confirmed_version_id IS NULL`（ADR-0004）
- 有效确认 = `confirmed_version_id != null && !stale`；批准时依赖校验是第二道防线（ADR-0005）
- `archive_version` 由 `cases.next_archive_version` 分配（ADR-0006）

## 待补（v1.3 已标 TBD，不属本 roadmap 主线）

- 认证授权模型、RBAC/ABAC
- `case.full.v1` 归档必需项细化
- 错误码完整目录
- 审计事件统一 schema、checkpoint 粒度、execution 重试策略
- 部署拓扑 / HA / DR / RPO / RTO / NFR
