> **归档文档（历史）**：本文件已于 2026-09-26 移入 docs/archive/，内容反映其写作时点状态，可能与现行实现不一致。现役入口见根 README.md 与 AGENTS.md。

# LexCyber 迭代交付计划

**现状日期：** 2026-09-19
**契约版本：** 0.8.0
**计划范围：** R1 本轮合入、R2 比赛线交付、R3 T3 解禁前置与模型接入配置、R4 发布加固
**定位：** 可审计的任务执行与案件材料工作台。辅助研判，不替代司法裁量；不产出量刑、责任或犯罪结论。

> 本文是可执行的轮次计划，不是已完成工作的证明。除「当前核验快照」明确列出的事实外，出口条件、远端 CI、推送和会签均须在相应轮次重新取得证据；不得把计划中的命令、历史产物或本地缓存状态写成已通过。

## 当前核验快照

本计划建立在以下仓库内事实之上：

- 当前检出的本地分支为 `main`，`HEAD` 为 `a078dead78d2fe96067af9112e5a415e61a11c70`（短哈希 `a078dea`）。本地 `origin/main` remote-tracking ref 为 `13c5ed4d31af4e1f4e54fcbc083fad33a6745467`；在本次核验未执行 `git fetch origin`，因此该引用不等同于刚从远端取得的实时状态。
- 按当前本地引用计算，`git rev-list --count main..origin/main` 为 `0`，`git rev-list --count origin/main..main` 为 `19`。这只能说明当前本地引用的拓扑关系；R1 推送前仍必须重新 `git fetch origin` 并再次计算。
- 最近三条提交为：`a078dea feat(web): complete auditable three-case experience`、`cd0e3ab fix(demo): finalize import restore and deployment hygiene`、`e230e78 fix(deploy): harden demo-cloud package after local rehearsal`。`PLAN.md` 规定的 `chore(submission): add single-container competition delivery` 当前尚未出现；`e230e78 fix(deploy)` 不替代该提交。
- 工作树不是干净工作树：已核验有比赛目录交付文件处于暂存状态，并有 `.env.v03.example` 修改。R1 不得把这些现状直接视为三个已整理提交；必须先按显式白名单复核暂存内容、排除密钥和原始材料，再拆成规定的提交。
- `.github/workflows/ci.yml` 当前定义五个作业：`test`、`java`、`web`、`contracts`、`compose-e2e`。本次没有查询远端 Actions 运行结果，因此本文不声明任何远端 CI 已通过。
- `scripts/quality_gate.py`、`scripts/quality_gate_checks.py`、根系统的模型探针/网关测试和 `V12__model_access_config.sql` 已存在；当前 `INTERNAL_RUNNERS` 仍为空，`tests/unit/test_model_chain_retention.py`、`tests/unit/test_quality_gate.py`、`tests/unit/test_delivery_plan_docs.py` 当前未找到。存在文件不等于已经通过相应出口条件。
- `docs/model-probe-record.md` 中已有一条历史记录，但它不是当前 R4 证据；R4 必须用当前 `.env.v03` 和当前 Compose 栈重新执行，并确认结果不是桩响应。
- 状态文档存在待对齐差异：`README.md` 与 `AGENTS.md` 仍把部分 T2 正式页描述为 `feat/case-import`，而 `docs/lexcyber-0.8.zh-CN.md` 与 `docs/lexcyber-0.8.en.md` 描述为本地 `main` 已接通。计划把这项对齐安排在 R2，届时以代码与契约为准，不预先宣称分支已合入。
- 当前本地可见的远端跟踪分支包括 `origin/codex/t1-api01-document-link`、`origin/dev`、`origin/feat/t1-round1`、`origin/feat/t1-round2`、`origin/feat/t2-round1`、`origin/feat/t2-round2`、`origin/feat/t3-round1`、`origin/feat/t3-round2`、`origin/feat/t3-round3`、`origin/feat/frontend-design-system`。分支处置只记录决策，不在本特性中删除分支。

## 计划不变量

- 不修改 `.github/workflows/ci.yml`；质量门定义集中在 `scripts/quality_gate_checks.py`，执行器为 `scripts/quality_gate.py`，映射测试只做单向漂移断言。
- 不改 `POST /v1/sources/search`、量刑任务创建、`compliance.analyze`、`conviction.analyze` 的 501 安全门闩；不改 `SENTENCING_ENABLED`、`LEGAL_SOURCE_SEARCH_ENABLED`、`MODEL_PROVIDER`、`WORKFLOW_PROFILE` 的 Compose 默认值。
- 不修改已发布 Flyway 迁移；数据库结构只能新增前向迁移，模型配置的本轮迁移为 `app` schema 下版本严格高于 11 的 `V12__model_access_config.sql`。
- 浏览器只调用 Java `/v1`；不得新增浏览器直连 Engine、MinIO 或内部 `/internal/` 接口的通路。`.env.v03`、API Key、原始法学材料和运行数据不得提交。
- 会签、远端 CI 确认、`git push origin main`、远端分支删除和线下评审均需要人类授权；本文只记录判据与动作，不在本任务中执行。

## R1 本轮合入轮

### 范围

R1 只处理 `PLAN.md` 所规定的三个提交整理、根系统门与比赛目录门通过、扫描门通过以及本地 `main` 到 `origin/main` 的非强制快进推送：

1. `fix(demo): finalize import restore and deployment hygiene`；
2. `feat(web): complete auditable three-case experience`；
3. `chore(submission): add single-container competition delivery`。

本轮不以本地 Compose 端到端或真实模型调用替代两套测试门；两者属于 R4 发布轮附加门。当前快照显示前两条规定提交已在最近提交中，第三条尚未形成，故 R1 不能因当前 `HEAD` 看起来接近目标而提前视为完成。

### 入口条件

- 先复核当前 `main`、`origin/main` 和工作树；必须执行 `git fetch origin`，不得沿用未刷新的 remote-tracking ref 做推送判断。
- 将比赛目录变更整理为独立的 `chore(submission)` 提交；不得把 `e230e78 fix(deploy)` 误记为该提交，也不得把当前暂存区直接提交为未经审计的混合提交。
- `git diff --check` 无报告；显式暂存白名单已复核，真实 `.env`、`demo-account.env`、API Key、私钥、镜像 tar、原始法学材料、缓存、构建产物和临时/断点文件均不在提交集合中。
- 根系统、比赛目录和扫描门的运行环境已准备；缺少工具时必须保留缺件名称，不能用新增跳过标记伪造通过。
- 任一入口条件未满足时，R1 不得开始推送；先完成对应的提交整理、暂存区清理或门禁修复。

**回滚判据：** 推送后 `git ls-remote origin refs/heads/main` 的哈希不等于本地 `HEAD`，或远端任一 CI 作业失败时，R1 保持未完成；使用新的前向提交修复，不重写已推送历史。

### 出口条件

| 判据 | 判定命令或判定产物 | 会签 |
| --- | --- | --- |
| 根系统门、比赛目录门和扫描门达到计划要求 | `python scripts/quality_gate.py`；目标退出码为 `0`。**该判据依赖可选实现项**：比赛语法扫描 runner 或 PyYAML 尚未具备时，只能按退回判据核对 `missing_tools` 仅为 `internal-runner:比赛语法扫描` 或 `PyYAML`，同时确认所有非可选检查已通过并记录待补项；不得把该条件带入 R4。 | — |
| 三个计划提交按名称落地 | `git log --oneline -3` 同时包含 `fix(demo)`、`feat(web)`、`chore(submission)`；当前快照尚不满足，第三条必须先形成。 | — |
| 暂存区无敏感信息、原始材料或超大文件 | `python scripts/quality_gate.py --gate scan` 退出码为 `0`；扫描失败时先按停止条件从暂存区移除命中路径，再同轮更新 `.gitignore` 或 `.dockerignore`。 | — |
| 推送前远端未领先 | `git fetch origin` 后 `git rev-list --count main..origin/main` 输出 `0`；若大于 `0`，停止推送并重新比较差异。 | — |
| 仅以快进方式推送 | 人类授权后执行 `git push origin main:main`，命令不得带 `--force` 或等价参数；推送动作不由本任务代执行。 | — |
| 推送后远端哈希一致 | `git ls-remote origin refs/heads/main` 的哈希等于 `git rev-parse HEAD`；若不一致，不宣称合入完成，改用前向修复提交。 | — |
| 远端五作业通过 | GitHub Actions `ci` 的 `test`、`java`、`web`、`contracts`、`compose-e2e` 均有成功运行记录；当前未查询该状态，不能预填通过。 | — |
| 模型链路保留 | `python -m pytest -q tests/unit/test_model_probe.py tests/unit/test_model_gateway.py tests/unit/test_model_chain_retention.py` 退出码为 `0`；守卫必须覆盖五项 `MODEL_*` 配置在四处同名可读、Compose 桩模式默认值，以及 `EngineDispatcher` 的 `"model.probe"` 到 `"model_probe"` 映射。`test_model_chain_retention.py` 是必做项，缺失即未满足。 | — |

### 产物清单

- 三个按白名单整理的提交，其中比赛目录为独立交付提交；
- 根系统门、比赛目录门、扫描门的输出与缺件记录；
- `docs/iterative-delivery-plan.md`、`docs/legal-signoff-checklist.md`、`scripts/quality_gate.py`、`scripts/quality_gate_checks.py` 及对应测试产物；
- 若获得人类授权，快进后的远端 `main` 哈希和五作业 CI 运行链接。未取得授权或未验证 CI 时只保留待办，不填写完成状态。

### 负责轨道

- **T1：** 根系统 Java/契约门、门禁脚本与边界守卫、数据库和异步任务相关测试。
- **T2：** Vue 依赖、类型检查、单测、构建，以及比赛目录前端交付内容。
- **T3：** Engine 模型探针、模型网关、三案数据和适配器保留核查。

## R2 比赛线交付轮

### 范围

R2 限定为 `competition_submission/1-智能体作品及其完整材料/` 的单容器交付线：包括交付完整性、比赛目录 Python/Java/web 测试、两份比赛契约和语法检查。该交付线独立于根系统契约版本 `0.8.0`；比赛目录 `src/contracts/` 是自己的交付快照，不把比赛目录特有的 `case.assist.analyze` 或 trace 接口反向复制到根系统。

### 入口条件

- R1 的三个提交整理、根系统门、比赛目录门、扫描门和推送前审计均已满足；未满足时 R2 不得开始，必须先完成 R1 的前序条目。
- 比赛目录构建上下文只包含允许的产品源码、测试、文档和示例，不能包含 `node_modules`、`target`、`dist`、缓存、真实环境文件或原始法学材料。
- 状态文档对齐工作已列入本轮；在对齐完成前，不把 README、AGENTS、中英文 0.8 文档相互矛盾的轨道描述作为最终事实。
- R2 不改变根系统契约版本、安全门闩或 Compose 默认值。

**回滚判据：** 比赛目录门任一检查项失败且修复需要改动根系统源码时，退回该根系统改动，比赛目录以独立快照方式修复；若变更已推送，只能用新的前向提交处理。

### 出口条件

| 判据 | 判定命令或判定产物 | 会签 |
| --- | --- | --- |
| 比赛交付完整性通过 | 在比赛目录执行 `python tests/acceptance/verify_delivery.py`，退出码为 `0`。 | — |
| 比赛目录门达到计划要求 | `python scripts/quality_gate.py --gate submission` 退出码为 `0`。**该判据依赖可选实现项**：比赛语法扫描 runner 或 PyYAML 缺失时，退回核对为其余九项全部通过、`missing_tools` 仅列 `internal-runner:比赛语法扫描` 或 `PyYAML`，并保留待补项记录；该条件不是 R4 发布轮的通过替代物。 | — |
| 单容器交付可构建 | 在比赛目录执行 `docker build -t lexcyber-submission .` 成功；构建上下文和生成镜像内不包含缓存、依赖目录、密钥或原始材料。 | — |
| 交付扫描通过 | `python scripts/quality_gate.py --gate scan` 退出码为 `0`；任一命中先 `git restore --staged <路径>`，再更新忽略规则并重新运行。 | — |
| 状态文档集对齐 | 必做判定产物为 `README.md`、`AGENTS.md`、`docs/lexcyber-0.8.zh-CN.md`、`docs/lexcyber-0.8.en.md`：四份均有现状日期、契约版本 `0.8.0`、四处 501 现状，且 T2/T3 轨道描述与代码/契约一致；**该判据依赖可选测试项**的自动补充为 `python -m pytest -q tests/unit/test_delivery_plan_docs.py`，该测试缺失时退回人工逐项核对四份产物，不得反向编造测试通过。 | — |
| 模型链路保留 | 沿用 R1 的同一组五字段、网关、路由、探针、Java 映射核对；比赛目录不能以独立快照覆盖或删除根系统调用位置。 | — |

### 产物清单

- 比赛目录单容器交付快照、构建结果和交付完整性报告；
- 比赛目录门与扫描门输出；
- 已对齐的四份状态文档，明确 T2 正式页的真实分支/合入状态、T3 适配器与 `demo_cases/three_case_demo` 的存在状态；
- 根系统契约 `0.8.0` 与比赛目录独立契约边界的核对记录。

### 负责轨道

- **T1：** 比赛目录 Java、契约、验收脚本、容器入口及根/比赛边界。
- **T2：** 比赛目录 Vue 类型检查、单测、构建和交付说明。
- **T3：** 比赛目录 Engine 适配器、三案数据、知识库来源与模型链路快照。

## R3 T3 解禁前置轮

### 范围

R3 限定为两条并行主线：

- 检索、量刑、`compliance.analyze`、`conviction.analyze` 的会签前置材料、契约/测试/审计准备；
- 模型接入配置接口与模型接入配置表单，负责轨道为 T1 与 T2。

R3 不改变四处公开安全门闩的默认返回码，不改变 `SENTENCING_ENABLED` 与 `LEGAL_SOURCE_SEARCH_ENABLED` 的默认取值；配置表单只负责安全的配置读写与验证，不负责解禁。

### 入口条件

- R2 全部出口条件已满足；若比赛线、状态文档或扫描门未完成，R3 不得开始，必须先回到 R2 修复。
- `docs/legal-signoff-checklist.md` 的 `SIGNOFF-001` 至 `SIGNOFF-005` 已建档，状态可以仍为「待签」；建档不等同于法学会签或公开口解禁。
- `.env.v03` 不得进入提交；模型配置接口的 API Key 只能通过受保护请求进入服务端密文存储，不能写入受版本控制文件。
- 任何配置存储或前端改动都必须保留 Java `/v1` 边界、Bearer 鉴权和四处 501 语义。

**回滚判据：** 若观测到四处公开口在默认开关下返回非 501，或 `SENTENCING_ENABLED` / `LEGAL_SOURCE_SEARCH_ENABLED` 任一默认值被改动，立即停止 R3；未推送改动退回工作树，已推送改动用新的前向提交恢复安全边界。

### 出口条件

| 判据 | 判定命令或判定产物 | 会签 |
| --- | --- | --- |
| 公开/内部契约与类型快照一致 | `openapi-spec-validator contracts/public-api.yaml && openapi-spec-validator contracts/internal-engine-api.yaml && python scripts/check_openapi_snapshot.py` 退出码为 `0`；公开响应不含 API Key 原值字段，内部明文配置口只在 Compose 内网和 service token 保护下可达。 | — |
| 数据库变更是前向迁移 | `git diff --name-status origin/main -- server/src/main/resources/db/migration` 对本特性只允许新增 `app/V12__model_access_config.sql`；既有 `V1`–`V11` 不得修改，迁移版本号互不重复且新版本严格大于 `11`。 | — |
| 配置读写、加密与审计安全 | `mvn -B test -Dtest=ModelAccessServiceTest,SecretBoxTest`（工作目录 `server`）通过。**该判据依赖可选测试项**：测试类未落地时退回必做产物判据——读取响应不含 `apiKey` 键、`apiKeyMask` 固定为 `********`、写入 API Key 只落密文、审计只含变更字段/供应商/模型/指纹等非原值信息。 | — |
| 前端表单和验证轮询 | `npm run typecheck` 与 `npm test`（工作目录 `web`）通过。**该判据依赖可选测试项**：新增模型表单测试未落地时退回既有前端测试加人工核对五字段校验、密码输入置空、`/v1` 请求边界和轮询终态；不能把缺失测试写成已通过。 | — |
| 四处安全门闩不受配置写入影响 | 必做 `mvn -B test -Dtest=TaskPoliciesTest`（工作目录 `server`）通过；可选的 `ModelAccessGateInvarianceTest` 若存在则一并执行。检索、量刑、`compliance.analyze`、`conviction.analyze` 仍分别保持现有 501 错误码。 | [SIGNOFF-001](../legal-signoff-checklist.md#signoff-001)、[SIGNOFF-002](../legal-signoff-checklist.md#signoff-002)、[SIGNOFF-003](../legal-signoff-checklist.md#signoff-003)、[SIGNOFF-004](../legal-signoff-checklist.md#signoff-004)、[SIGNOFF-005](../legal-signoff-checklist.md#signoff-005) |
| 默认开关与 501 门闩无变化 | `git diff origin/main -- docker-compose.yml .env.v03.example` 中 `SENTENCING_ENABLED`、`LEGAL_SOURCE_SEARCH_ENABLED`、`MODEL_PROVIDER`、`WORKFLOW_PROFILE` 的默认取值未被改变；公开门闩相关测试仍通过。 | — |
| 解禁前置材料完整 | `docs/legal-signoff-checklist.md` 的五条记录均有非空「解禁后验收动作」，且主表记录安全门闩、默认开关、状态、返回码和解禁归属轮次；未签署期间仍写明 501。 | [SIGNOFF-001](../legal-signoff-checklist.md#signoff-001)、[SIGNOFF-002](../legal-signoff-checklist.md#signoff-002)、[SIGNOFF-003](../legal-signoff-checklist.md#signoff-003)、[SIGNOFF-004](../legal-signoff-checklist.md#signoff-004)、[SIGNOFF-005](../legal-signoff-checklist.md#signoff-005) |
| 模型链路保留 | R1 的必做保留命令通过；若新增 `tests/unit/test_model_access.py` 已落地，则另执行该测试验证环境变量回退、内部口失败回落、覆盖后网关 URL/Authorization 头仍保持原行为。新增测试属于可选补充，缺失时退回 R1 的必做源文件/既有测试核对，不得退回删除模型接入配置。 | — |

### 产物清单

- `/settings/model-access` 公开契约、内部 Engine 配置契约和 `web/src/api-types.ts` 快照；
- Java 侧 `SecretBox`、配置 DTO/Store/Service、公开控制器、内部配置控制器和 `V12` 前向迁移；
- Engine 有效配置回退模块、保留原有 `ModelGateway`/`ModelRouter`/`ModelProbeRunner` 行为的实现与测试；
- Vue 模型接入表单、路由入口、配置 API 函数、校验/错误提示和轮询状态机测试；
- 五条会签前置材料与不改变四处 501、两个默认开关的审计证据。

### 负责轨道

- **T1：** 公开/内部契约、Java 密文存储和审计、前向迁移、Engine 配置读取与安全门闩测试。
- **T2：** 模型接入配置 API 调用、表单校验、引导态、连通性验证轮询、错误提示和鉴权路由。
- **T3：** Engine 配置回退、ModelGateway/ModelRouter/ModelProbeRunner 链路与适配器会签前置材料。

## R4 发布加固轮（发布轮）

### 范围

R4 是发布轮，范围为发布前加固、日常三门复核、本地 Compose 端到端复核和真实 `model.probe` 复核。真实模型模式只由发布操作者在本地 `.env.v03` 显式开启；桩模式仍是 Compose 的默认运行模式。

### 入口条件

- R3 全部出口条件满足，模型接入配置与安全门闩已经过测试和产物核对；未满足时 R4 不得开始。
- 发布操作者在未提交的本地 `.env.v03` 中确认 `MODEL_PROVIDER` 非 `stub`、`MODEL_API_KEY` 非空，并配置 `MODEL_CONFIG_ENCRYPTION_KEY`；本文不读取、不记录这些值。
- Docker/Compose、Python 3.12、Java、Node/npm、OpenAPI validator 等发布轮工具可用；真实模型端点可从 Engine 运行环境访问。
- 既有历史 `docs/model-probe-record.md` 只能作为格式参考，不能替代本轮当前配置下的非桩调用证据。

**回滚判据：** 本地 Compose 端到端失败、真实 `model.probe` 失败或 `content.provider` 为 `stub` 时，停止 R4 推送；已推送的发布改动只能用新的前向提交撤回，不能以桩响应替代发布证据。

### 出口条件

| 判据 | 判定命令或判定产物 | 会签 |
| --- | --- | --- |
| 日常三门全绿 | `python scripts/quality_gate.py` 退出码为 `0`；可选比赛语法 runner/PyYAML 的条件退回规则只能用于日常轮记录，发布轮不得以缺 runner 作为通过。 | — |
| 发布轮两项 runner 均已落地且全绿 | `python scripts/quality_gate.py --gate release --release` 退出码为 `0`，同时完成本地 Compose 端到端和真实 `model.probe`；两个发布轮 runner 缺失、Docker 不可用、凭据缺失或任一失败均停止 R4，**不接受有条件通过**。 | — |
| 本地 Compose 端到端与复核链路通过 | 依次执行 `docker compose --env-file .env.v03 -f docker-compose.yml up -d --build`、就绪检查、`python scripts/t1_local_closeout.py http://127.0.0.1:18080`，并复核任务进入 `waiting_review` 后 approve 回到 `completed`；无论成功失败均执行 `docker compose -f docker-compose.yml logs --no-color`（先掩码）和 `docker compose -f docker-compose.yml down -v`。 | — |
| 真实探针产物有效 | 经 Java `/v1` 登录、创建 `metadata.taskType=model.probe` 任务、最多 `60` 次每次 `2` 秒轮询，再只在 `completed` 时读取 `/result`；`docs/model-probe-record.md` 含 `taskId`、`resultId`、`provider`、`model`、`latencyMs`、`schemaVersion` 六个字段，`provider` 非 `stub`，不含密钥。 | — |
| 远端五作业通过 | GitHub Actions `ci` 的 `test`、`java`、`web`、`contracts`、`compose-e2e` 全部成功；当前未验证，发布轮必须以本轮远端记录为准。 | — |
| 模型链路保留与真实模型模式连通性 | R1 的同一组保留核对通过，并以本轮真实 `model.probe` 的三项合取判据作为同一出口证据：模型 provider 非空且非 `stub`、任务终态为 `completed`、结果 `content.provider` 非 `stub`。任一条件不成立即未通过。 | — |

### 产物清单

- 发布轮质量门的逐项输出、Compose 日志清理记录和端到端复核结果；
- 当前 `.env.v03` 配置下重新生成的 `docs/model-probe-record.md`，只含六项探针白名单字段及必要的记录时间格式，不含 API Key；
- 远端 CI 五作业成功记录；
- 发布前分支哈希、扫描结果、契约快照和安全门闩复核记录。

### 负责轨道

- **T1：** 发布门编排、Java 公开 API/任务生命周期、审计、数据库迁移和 CI 结果确认。
- **T2：** 前端生产构建、登录/配置/探针 UI 冒烟和浏览器边界复核。
- **T3：** Engine/Compose、真实模型出口、模型探针、三案演示链路和日志掩码复核。

## 日常门与发布轮门定义

日常轮次的本地门固定为根系统门、比赛目录门和扫描门：

- **根系统门：** `python -m ruff check .`、`python -m pytest -q -m "not integration"`、`server/` 下 `mvn -B test`、`web/` 下 `npm ci` / `npm run typecheck` / `npm test` / `npm run build`、公开与内部 OpenAPI validator、`python scripts/check_openapi_snapshot.py`，以及三案数据、导入包安全限制、租约 fencing、事件材料回填、量刑重放、模型探针/网关和模型路由映射保留检查。`ruff` 的范围由仓库配置排除比赛快照，不重复扫描同一源码。
- **比赛目录门：** `tests/acceptance/verify_delivery.py`、排除 `integration` 与 `e2e` 的 Python 测试、比赛目录 Java 测试、web 四连、两份比赛契约校验和 JSON/YAML/Python 语法扫描。`pytest.ini` 当前只声明 `integration`，`e2e` 表达式的兼容性由检查项备注记录，不通过修改比赛目录规则掩盖。
- **扫描门：** 只检查已暂存文件；拒绝真实 `.env`/`demo-account.env`、私钥/令牌/内联密钥、`deploy/ecs-upload.tar`、镜像 tar、部署运行数据、原始 `法学材料/` 与 `.tmp-legal-docs/`、依赖/构建/缓存目录、临时/断点文件和超过 100 MB 的单文件。允许清单不是豁免通道，deny 规则优先；`.t1-*` 和 `.tmp-*` 根级文件仍按规则命中。命中输出文件路径和规则名称，疑似密钥值只显示掩码。
- **发布轮门：** 只在显式 `--release` 时执行，额外包含本地 Compose 端到端和真实 `model.probe`。不带 `--release` 时发布项必须显示跳过；R4 不能把跳过当通过。

质量门执行器按每个检查项给出「通过 / 失败 / 跳过」三态：失败退出码为 `1`，无失败但存在缺工具或缺 runner 时为 `2`，全部通过为 `0`。命令输出只保留经统一 `mask()` 处理的末 40 行；`.env.v03` 的非空值只能作为掩码源，不能在摘要、日志、审计或文档中回显。Windows `WinError 5` 只能归类为失败并提示 Linux/WSL 复跑，不能归类为通过。

发布轮的请求边界固定为：登录 `POST /v1/auth/login` 取得 Bearer，之后的 `POST /v1/tasks`、`GET /v1/tasks/{id}`、`GET /v1/tasks/{id}/result` 一律经 `http://127.0.0.1:18080/v1` 并携带 `Authorization: Bearer`；健康检查只能调用同一 Java 基址下的 `/healthz`。门脚本不得直连 Engine、MinIO 或内部 `/internal/` 口。

## 分支与合入策略

- 本地 `main` 到 `origin/main` 只允许快进推送。推送前先执行 `git fetch origin`，再执行 `git rev-list --count main..origin/main`；输出大于 `0` 时停止推送，重新比较本地与远端差异，不自动合并或覆盖。
- 普通推送命令为 `git push origin main:main`，不得使用 `--force`、`--force-with-lease` 或其他重写远端历史的等价参数。推送后执行 `git ls-remote origin refs/heads/main`，远端哈希必须等于本地 `git rev-parse HEAD`。
- 通过 Pull Request 合入时，PR 描述必须同时包含：变更摘要、已执行的门禁命令、每条门禁命令的结果。远端 CI 结果以本轮实际运行记录为准，不以本地缓存或历史记录替代。
- 提交只使用显式白名单暂存指定文件，例如 `git add -- <明确列出的文件>`；禁止 `git add .`、全目录暂存或把 `.env.v03`、原始法学材料和运行数据混入提交。暂存前后分别检查 `git diff --cached --name-status`、文件体积和扫描门结果。
- 推送 `main`、远端 CI 确认、法学会签和远端分支清理均需要人类授权；本计划只规定验证动作，不把授权动作自动化。

## 远端分支处置

以下是按需求列出的远端分支决策。当前范围内不删除任何分支；标为「待清理」的分支保持存在，删除由后续单独决策执行。`origin/codex/t1-api01-document-link` 的保留解除条件为缺失契约、smoke 与测试断言已经移植并由门禁验证。

| 远端分支 | 决策 | 前置条件或说明 |
| --- | --- | --- |
| `origin/codex/t1-api01-document-link` | 保留 | 缺失契约、smoke 与测试断言全部移植并验证后，才另行评估解除保留。 |
| `origin/dev` | 保留 | `ci.yml` 的 push 触发器包含 `dev`；删除会改变 CI 触发语义。 |
| `feat/t1-round1` | 待清理 | 对应远端跟踪引用 `origin/feat/t1-round1`；本特性范围内保持存在，不在本轮删除。 |
| `feat/t1-round2` | 待清理 | 对应远端跟踪引用 `origin/feat/t1-round2`；本特性范围内保持存在，不在本轮删除。 |
| `feat/t2-round1` | 待清理 | 对应远端跟踪引用 `origin/feat/t2-round1`；本特性范围内保持存在，不在本轮删除。 |
| `feat/t2-round2` | 待清理 | 对应远端跟踪引用 `origin/feat/t2-round2`；本特性范围内保持存在，不在本轮删除。 |
| `feat/t3-round1` | 待清理 | 对应远端跟踪引用 `origin/feat/t3-round1`；本特性范围内保持存在，不在本轮删除。 |
| `feat/t3-round2` | 待清理 | 对应远端跟踪引用 `origin/feat/t3-round2`；本特性范围内保持存在，不在本轮删除。 |
| `feat/t3-round3` | 待清理 | 对应远端跟踪引用 `origin/feat/t3-round3`；本特性范围内保持存在，不在本轮删除。 |
| `feat/frontend-design-system` | 待清理 | 对应远端跟踪引用 `origin/feat/frontend-design-system`；本特性范围内保持存在，不在本轮删除。 |

## 停止条件与失败处理

| 触发条件 | 必须动作 | 禁止动作 |
| --- | --- | --- |
| `quality_gate.py` 退出码非 `0` | 停止本轮推送，保留失败输出和掩码后的诊断，修复失败原因后从对应门重新运行。 | 不移除检查项、不放宽断言、不新增跳过标记。 |
| 扫描门失败 | 停止本轮提交；先执行 `git restore --staged <命中路径>`，再在同轮更新 `.gitignore` 或 `.dockerignore`，重新扫描。 | 不把命中路径加入临时豁免、不上传原始法学材料、不用密钥替换密钥。 |
| 远端任一 CI 作业失败 | 本轮保持未完成，定位并修复原因后重新确认全部受影响作业。 | 不把历史绿灯、局部绿灯或未运行当作全绿。 |
| Windows 子进程出现 `WinError 5` | 以 Linux 或 WSL 的 Python 3.12 环境复跑同一命令；质量门原结果仍为失败/非零，直到复跑结果可解释。 | 不把平台权限错误标为通过，不删除检查项。 |
| 已推送提交需要撤回 | 创建新的前向提交撤回变更，保留已推送历史。 | 不 `reset --hard`、不强推、不重写远端历史。 |
| 变更涉及数据库结构 | 新增前向 Flyway 迁移，核验版本单调递增和旧迁移未改。 | 不修改任何已发布迁移，不手工在运行库绕过 Flyway。 |
| 会签尚未完成 | 实现与测试可继续作为前置工作推进，但公开检索、量刑、合规、定罪能力继续保持 501，默认开关继续关闭。 | 不以页面已接通、适配器已存在或单侧开关开启作为解禁。 |

所有失败处理仅限于修复失败原因；不得强制推送、删除远端分支、上传原始法学材料、降低门槛或掩盖失败。

## 会签与公开安全边界

会签清单由 [`docs/legal-signoff-checklist.md`](../legal-signoff-checklist.md) 独立维护。五条事项的出口引用如下：

- [`SIGNOFF-001`](../legal-signoff-checklist.md#signoff-001)：检索公开口；未签署时 `POST /v1/sources/search` 返回 `501 SOURCE_SEARCH_UNAVAILABLE`，默认 `LEGAL_SOURCE_SEARCH_ENABLED` 保持关闭。
- [`SIGNOFF-002`](../legal-signoff-checklist.md#signoff-002)：量刑公开口；未签署时量刑任务创建返回 `501 SENTENCING_UNAVAILABLE`。解禁后必须同时验证 Java 与 Engine 两侧开关；只开 Java 侧会建成任务但可能被 Engine 标为 `failed`，不构成验收通过。
- [`SIGNOFF-003`](../legal-signoff-checklist.md#signoff-003)：`compliance.analyze`；未签署时保持 `501 COMPLIANCE_UNAVAILABLE`。
- [`SIGNOFF-004`](../legal-signoff-checklist.md#signoff-004)：`conviction.analyze`；未签署时保持 `501 CONVICTION_UNAVAILABLE`。
- [`SIGNOFF-005`](../legal-signoff-checklist.md#signoff-005)：文书字段字典；字段语义、`draftType`、`templateVersion` 和复核归档边界完成会签前，不把文书草稿空壳当作正式法律结论。

实现工作在会签完成前继续推进，但只作为解禁前置工作；不能改四处 501、不能改变两个开关默认关闭状态，也不能产出量刑、责任或犯罪结论。

## 模型配置与调用链路约束

- 五项配置始终保持可追踪：`MODEL_PROVIDER`、`MODEL_NAME`、`MODEL_API_KEY`、`MODEL_API_BASE_URL`、`MODEL_TIMEOUT_SECONDS`。它们在 `.env.v03.example`、Compose 的 `engine` 与 `engine-worker` 环境段、`config/settings.py`、`engine/settings.py` 中保持同名可读；Compose 的 `WORKFLOW_PROFILE` 与 `MODEL_PROVIDER` 默认均为 `stub`。`.env.v03` 的真实模式只能由本地操作者显式开启，不能提交。
- `models/gateway.py` 必须从配置拼接 `MODEL_API_BASE_URL.rstrip('/') + '/chat/completions'`，以 `Authorization: Bearer` 携带 API Key；`models/router.py` 保留 provider/model 主路由和 `stub` 备用路由；`engine/model_probe.py` 保留 `fallback=False` 和探针字段行为；Java `EngineDispatcher` 保留 `metadata.taskType == 'model.probe'` 到 Engine `model_probe` 的映射。
- 桩模式与真实模型模式共存，切换只由模型配置取值决定。`openai` 且 API Key 为空时必须保持 `MODEL_NOT_CONFIGURED`，超时保持 `MODEL_TIMEOUT`，其他调用失败保持 `MODEL_FAILED`。不把端点、模型名或密钥写成源码固定值。
- 发布轮真实调用只经 Java `/v1`，`content.provider == 'stub'` 一律不是真实模型证据。探针产物只允许 `taskId`、`resultId`、`provider`、`model`、`latencyMs`、`schemaVersion` 六个业务字段，不保存 `echo`、`tokenUsage` 或任何凭据。
- `MODEL_MAX_RETRIES` 保留现有配置默认值，但不纳入本轮五字段配置表单，因为当前 `ModelGateway` 没有实际消费者；将来若增加真实重试语义，另立需求、契约和测试。
- 已知安全弱点：当前认证模型没有角色/管理员权限，任何有效会话都可能改写全局模型出口和密文 API Key。该弱点必须登记为后续加固项（引入管理员角色/权限模型），本特性不以隐含角色或前端隐藏按钮假装解决。

## 回滚与证据规则

每轮只接受可复核证据：命令退出码、测试报告、契约/快照差异、扫描摘要、远端 CI 运行记录、远端哈希或会签清单记录。历史记录、未刷新的 remote-tracking ref、未执行的命令、页面存在或本地未提交文件均不能代替出口证据。

若某轮入口未满足，回到所列前序轮次或前序条目，不跨轮强行推进；若已推送变更需撤回，使用新的前向提交；若数据库需要调整，继续新增前向迁移。任何回滚都不得通过降低检查强度、删除检查项、强推、删除分支或上传原始材料完成。
