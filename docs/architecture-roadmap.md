# LexCyber 架构演进 Roadmap（v1.3 实施）

> 本文件承载 v1.3 §0.2 明确排除出架构书的「交付状态 / 阶段 / 进度」内容。
> 目标架构唯一权威：`LexCyber-system-architecture-v1.3-postgresql-physical-model.md`。
> 矛盾裁决：`docs/adr/ADR-0001` ~ `ADR-0006`。

## 基线

- 冻结点 tag：`arch-v13-baseline`（main `a078dea`）
- `competition_submission/`、`本科生组+…/`：冻结快照，不再与主树同步
- `/v1` 契约：冻结为读取兼容层；新生命周期端点走 `/v2`

## 2026-10-08 main 修复验证（进行中）

审核基线为 `8aadc846174436f88b5ab388e3c5a5d1fe755e01`。该提交 CI 五项全通过，但遗漏了文书批准、旧 execution 迟到发布、渲染输入依赖竞态及多规则量刑阻断展示。

- 修复分支 `codex/repair-main-lifecycle`：渲染文书使用 UUID 描述符与 head；V21 前向迁移保留旧流及历史版本，将不可验证的旧待审稿关闭为 superseded，要求重新生成。
- 派发冻结有效已确认模块的 payload 和 artifact version ID；渲染回调仅绑定实际输入版本，审批再次校验事实与模块依赖。未会签能力继续 fail-closed。
- 旧 execution 不发布；失败回调不发布；回调重放不新建复核或回退已完成执行。复核决策校验请求版本。
- 前端整体 blocked 不输出刑期，各规则结果可追溯；开发服务器同时代理 `/v1` 和 `/v2`；任务轮询隔离旧路由响应。
- 事实工作副本新增历史、diff 和版本回写入口；切案后清理旧编辑及请求，工作副本与已确认快照比对后再显示确认状态。事实写入使用契约中的复数实体路径。复核详情改用案件归档，展示固化的 manifest，不再调用退役的单条复核归档。
- 空案件归档返回可定位的事实缺口；未知 archive profile 拒绝。归档创建与读取使用一致的公开字段。v2 模块/文书派发响应状态与公开契约一致。v2 任务重试重验能力、保留冻结输入，依赖变更后要求重新派发；不能混用旧快照与新事实引用。
- v2 OpenAPI 响应补齐必需描述并接入合同 CI。Compose 验证使用明确标注的隔离 CI 规则/模板，实际驱动模块、文书、批准和归档；§19 检查要求确认、回调重放及复核/归档并发，必需检查 SKIP 不再算验收成功。测试 fixture 不构成正式法学批准。
- 续查归档：按照权威 §5.11 强制要求三个有效模块与批准文书，不能仅有 facts 就创建完整归档；已有过期文书继续阻断。同一 manifest 在案件行锁内复用原归档，不增加版本号。并发脚本使用完整四工件 fixture，注册表 8 项数据库集成测试接入迁移后的 Compose 环境，数据库不可达即失败。
- 提交 `3adfe52` 的 CI `37670947026`：Python、web、contracts 成功；Java 107 项中 1 错误，重复归档触发 manifest 唯一约束；Compose 因此前置失败未运行。本次补丁修复该真实错误，不通过删约束或放宽测试绕过。
- 已验证的提交 `7f87848`：CI `37665658080` 五个 job 成功；Java/Postgres 99 项测试、0 跳过，其中 V20→V21 历史迁移和文书上游发布/审批竞态均实际执行。后续新增的重试、归档、事实界面和完整 Compose/§19 验证仍待新提交 CI 收口。规则/模板正式会签、B/C 映射和量刑基准校正仍按法学待签清单办理，不能由代码修复代替。

本节记录进行中的工作，不替代下面的历史实测，也不证明全部功能已完成验证。

## 阶段状态

| 阶段 | 内容 | 状态 |
|---|---|---|
| 0 | 决策收口 + 基线冻结 | ✅ 完成：ADR-0001..0006、tag `arch-v13-baseline`、roadmap、文档指针 |
| 1 | 主键迁移到 uuid（V13 + legacy_id_map） | ✅ 已在开发库应用并实测（e2e 全链路 uuid 主键） |
| 2a/2b | 五张实体表 + FactsVersion/FactsHead | ✅ 已在开发库应用；全量快照 + CAS + diff/clone 实测通过 |
| 3 | ArtifactStream/ArtifactVersion + 依赖表 + execution_publication + 三套结果合并 | ✅ 发布幂等实测；模块/文书结果经 `publishModuleArtifact` 发布 |
| 4 | ModuleHead/DraftHead + 有效确认判定 + stale 传播 | ✅ 实测：facts 变更 → 工件 stale → 旧工件批准被 DEPENDENCY_STALE 拦截 |
| 5 | ReviewRecord 改绑 artifact_version_id + CaseArchive | ✅ 实测：复核裁决 → effectivelyConfirmed → `case.full.v1` 归档（manifestHash） |
| 6 | engine.execution 契约分离 + fencing + outcome envelope | ✅ engine V5 应用；waiting_review 展示态经 output_envelope 映射 |
| 7 | 统一幂等 + `/v2` 契约 + 前端迁移 + 删多 key 容错层 | ✅ 基本完成：V19 + IdempotencyService + `/v2`（18 paths）+ 前端逐页迁移 + `apiV2` 契约测试；payload schemaVersion 已在契约冻结（枚举），前端新增 `module-content-v2.ts` 严格读取器 + `RuleResultsPanel`（v2 工件此前在模块页显示为空——容错键不命中，现已修）；`module-content.ts` 容错层仅留 /v1 演示壳用途；文档/任务轮询/复核队列保留 /v1 兼容读层 |
| 8a | 法源/规则/模板注册与会签（P5 前置基建） | ✅ 代码完成并在真实库验证。engine/V6 注册表（legal_source + alias + supersession 链 + rule_package + template_package + signoff_record）+ `engine/rules/registry.py` + `/internal/v1/capabilities` 等 6 个内部端点 + `EngineCapabilitiesClient`；`/v2` 模块派发已接真实能力门闩（无 approved 规则 → `MODULE_EXECUTION_UNAVAILABLE`，有能力但适配器未实现 → `ENGINE_ADAPTER_PENDING`） |
| 8b | 规则层（合规/定罪/界分执行体） | ✅ 第一片已验证：evaluator DSL + `module_analysis.py` → case.*.v2 payload + 逐条件 trace + fired 规则双时点法源解析；e2e 实测 calculated/not_applicable/blocked 三态。剩余：规则语料扩充（当前 7 条底稿） |
| 8c | 可解释量刑（注册表化） | ✅ 第一片已验证：base_tiers 择档 + when-gated adjustments + 显式夹逼留痕 + ROUND_HALF_UP，产出 sentencing.v2；旧 metadata 重放保留兼容。剩余：地方细则插件、缓刑/罚金独立计算块 |
| 8d | 文书渲染 | ✅ 第一片已验证：`draft.render` → draft.v2 + 占位符阻断 + 上游 payload 代入；模板按案型分（`indictment-assist` 通用 + `indictment-draft` 支付结算型，语料 `engine/rules/corpus/core_templates.json` + `seed --templates`）。剩余：下载导出 |
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

**本轮（收口整理）已落地**：

1. **V20 授权迁移**：`lex_app` 对 app schema 全部表/序列的 CRUD 授权 + migrator 新建对象默认授权，固化此前手工执行的 GRANT；角色缺失/权限不足时降级 WARNING 不炸迁移。
2. **`app-migrate` compose 服务**：app schema 迁移由 `lex_migrator`（POSTGRES_USER）执行，Java 启动 Flyway 仅校验——修复全新环境 `lex_app` 无 `pgcrypto` 权限导致的 V13 失败。engine/engine-worker 共用 `image: lexcyber-v03-engine:latest` 消除镜像漂移。
3. **`/v1` 模块写层退役**：PUT 模块壳 + POST confirm 默认 `410 MODULE_WRITE_RETIRED`，仅 `DEMO_IMPORT_ENABLED` 放行；契约标 deprecated；导入脚本容忍 410 记 `skipped_write_retired`。
4. **v2 payload schema 冻结**：`ArtifactVersionView.schemaVersion` 改枚举（document.parse.v1 / case.module.v1 / case.compliance.v2 / case.conviction.v2 / sentencing.v2 / draft.v2）；前端新增 `module-content-v2.ts` 严格读取器 + `RuleResultsPanel` 组件——此前 v2 工件在模块页全部显示为空（容错键不命中），现定罪/合规页展示规则逐条 fired + 逐条件 trace；AnalysisPage 金额改读确认事实快照（原读定罪 payload，v2 下本为空）；DocumentsPage 渲染结果走严格读取。
5. **模板按案型**：`engine/rules/corpus/core_templates.json` 新增 `indictment-assist` 通用模板（无 payment_settlement_amount 占位符）；`seed --templates` 播种路径。
6. **§19 并发脚本**：`scripts/concurrency_check.py`——双确认 CAS（409）、双发布重放（工件版本稳定）、归档/复核交错（无 5xx）；internal 用例需容器网内执行。
7. **文档归档**：11 篇历史文档 + 根 `PLAN.md` → `docs/archive/`（git mv 保历史 + 归档横幅）；`AGENTS.md`/`README.md` 按现状重写；`docs/legal-signoff-checklist.md` 补法学待签清单。

**仍待办**：案例 B/C 键化覆盖层（需法学审定映射）、真实法学负责人会签（当前 e2e 占位，含新增 `indictment-assist` 模板）、量刑基准档与案载裁量偏差校正（法学）、文书下载导出、§19 脚本在 CI/容器网内定期执行。

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
