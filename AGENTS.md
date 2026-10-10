# LexCyber — Agent 规则

可审计任务执行工作台。辅助研判，不替代司法裁量；不产出量刑 / 责任 / 犯罪终局结论。

**目标架构**：`LexCyber-system-architecture-v1.3-postgresql-physical-model.md`（唯一权威）。矛盾裁决见 `docs/adr/ADR-0001`~`0006`。实施进度见 `docs/architecture-roadmap.md`。历史文档在 `docs/archive/`。

## 怎么跑

```powershell
Copy-Item .env.v03.example .env.v03
docker compose --env-file .env.v03 up --build
```

入口 `http://127.0.0.1:18080`。健康检查 `GET /healthz`。**契约版本：** 0.8.0（/v1）+ /v2。**现状日期：** 2026-09-26。

迁移由一次性服务执行：`app-migrate`（lex_migrator，app schema）、`engine-migrate`（lex_engine，engine schema），Java 启动时 Flyway 仅做校验。

## 技术栈

- 公开 API：Java 21 / Spring（`server/`）
- 执行：Python Engine + Dramatiq（`engine/`）
- 前端：Vue（`web/`）
- 存储：Postgres（`app` / `engine` 分 schema）+ Redis + MinIO
- 契约：`contracts/public-api.yaml`（/v1 兼容读层）、`contracts/public-api-v2.yaml`（/v2 生命周期，现役入口）、`contracts/internal-engine-api.yaml`

## 目录与约定

- **现役**：`web/`、`server/`、`engine/`、`contracts/`、`nginx/nginx.v03.conf`、`infra/postgres/init/`
- **Engine 旧任务类型仍依赖**：`models/`、`graph/`、`skill_runtime/`、`skills/`、`retrieval/`；legal profile 链 `agents/`、`audit/`、`config/`、`prompts/`、`storage/`、`tools/`；v2 执行体（`engine/adapters/module_analysis.py`、`sentencing_v2.py`、`document_render.py`、`engine/rules/`）不依赖这些
- **边界**：浏览器只打 Java `/v1`/`/v2`，不直连 Engine / MinIO；`/internal/` 不经过 nginx
- 上传后只轮询 `parseTaskId`，正文只读 `GET /v1/tasks/{id}/result`。不要再创建解析任务，不要传 `storageKey`
- `document.parse` / `model.probe` 必须 Bearer。caseless stub 任务可无会话
- **能力门闩**：模块派发前置查询 Engine `/internal/v1/capabilities`——family 缺 approved 规则包 → `MODULE_EXECUTION_UNAVAILABLE`；适配器未实现 → `ENGINE_ADAPTER_PENDING`；Engine 不可达 → fail-closed。已取代 /v2 派发侧旧静态 501
- **/v1 遗留公开口门闩仍在**：检索 / 量刑 / 合规分析 / 定罪分析的 /v1 公开入口按未会签保持 `501`（`SOURCE_SEARCH_UNAVAILABLE` / `SENTENCING_UNAVAILABLE` / `COMPLIANCE_UNAVAILABLE` / `CONVICTION_UNAVAILABLE`）；只开 Java `SENTENCING_ENABLED` 会建成任务再被 Engine 标 `failed`。不要改默认开关假装已接通
- **`/v1` 模块写层（PUT module state / confirm）已退役**：默认 410 `MODULE_WRITE_RETIRED`；仅 `DEMO_IMPORT_ENABLED=true` 放行（三案演示导入脚本用）。结果只能来自执行→发布路径
- DB 只走 Flyway，**禁止改已应用迁移**（app V1–V20、engine V1–V6 已应用到开发库，仅前向新增）。app schema 迁移执行角色 = `lex_migrator`
- 密钥只进 `.env.v03`，禁止提交
- **engine 代码变更后必须 `docker compose build engine engine-worker`**——两服务共用镜像 `lexcyber-v03-engine:latest`，只 build 一个会漂移

## 冻结快照

`competition_submission/`、`本科生组+…/`：**自 `6ef7803`（2026-09-26）起冻结**，不再与主树同步，修改需单独说明理由。

## 测试

```powershell
# Java（需要可达的 Postgres；容器内跑 maven）
docker compose run --rm -e TEST_JDBC_URL=jdbc:postgresql://postgres:5432/lexcyber_test `
  -e TEST_JDBC_USER=lex_app -e TEST_JDBC_PASSWORD=<pwd> java mvn -B test
# 前端
cd web; npm ci; npm run typecheck; npx vitest run; npm run build
# Engine
python -m pytest -q            # 含 tests/integration 时需可达 engine 库
python -m ruff check engine/
# 契约
python -c "import yaml; yaml.safe_load(open('contracts/public-api-v2.yaml',encoding='utf-8')); yaml.safe_load(open('contracts/public-api.yaml',encoding='utf-8'))"
# §19 并发验证（公开用例经 nginx；双发布需容器网内）
python scripts/concurrency_check.py
```

## 当前状态（2026-09-26）

- **v1.3 生命周期已端到端实测**：facts 版本化（六实体快照 + CAS 确认 + diff/clone）、工件发布幂等（execution_publication）、stale 传播、复核裁决、归档——五段管道全通
- **规则注册表**（engine V6）：法源 + 新旧链 + 规则包/模板包 + 会签记录；approved/superseded 不可变；所有评审结论必须走 `signoff()`（`engine.signoff_authorized` GUC，直连 SQL 被拒）
- **v2 执行体**：合规/定罪/界分（`module_analysis.py`）、可解释量刑（`sentencing_v2.py`）、文书渲染（`document_render.py`）——只消费 approved 规则/模板 + 确认事实快照，恒 `human_review_required`
- **语料**：`engine/rules/corpus/core_rules.json`（7 条法学底稿）+ `core_templates.json`（文书模板）+ `engine/adapters/legal_sources.json`；播种 `python -m engine.rules.seed [--rules|--templates] <path>`，**当前会签人为占位 `e2e-reviewer`，非正式批准**
- **演示**：`scripts/import_three_case_demo.py` 导入三案（需 `DEMO_IMPORT_ENABLED=true` 才写模块壳）；案例 A/C 已注入键化覆盖层，B 案按行为人拆为 `demo-case-b-proceeds#huang`/`#chen` 注入
- **遗留缺口**：案载 12–18 月基准被复核裁定为偏重应修正（系统 9.0 月无异常，规则不改）；`module-content.ts` 容错读取器仅服务 /v1 演示壳（v2 工件用 `module-content-v2.ts`）；合规两规则依赖未会签的 `cn-cybersecurity-law-2025`，暂不进有效视图
- **2026-10-09 法学生复核版会签已入册**：10 法源 signed_off（别名修正+掩隐新旧链）、规则/模板同内容升版正式会签（旧版 superseded）；复核人非法学负责人，有条件同意的实质修改待负责人确认后另出新版本。明细见 `docs/legal-signoff-checklist.md`、`docs/legal-review/`、执行脚本 `scripts/apply_legal_signoff_2026_10_09.py`

下一步：1.1.0 补充规则和 `cn-cybersecurity-law-2025` 仍是 pending，须法学负责人 `signoff()` 后才进入有效视图；文书四类模板与页面辅助研判措辞见 `docs/legal-supplement-requirements-2026-10-10.md`。不要把 pending 语料当成已会签，也不要打开 `/v1` 的 `501` 门闩。
