# LexCyber — Agent 规则

可审计任务执行工作台。辅助研判，不替代司法裁量；不产出量刑 / 责任 / 犯罪结论。

**目标架构**：`LexCyber-system-architecture-v1.3-postgresql-physical-model.md`（唯一权威）。矛盾裁决见 `docs/adr/ADR-0001`~`0006`。实施进度见 `docs/architecture-roadmap.md`。`docs/architecture-1.0.zh-CN.md` 已被取代。

## 怎么跑

```powershell
Copy-Item .env.v03.example .env.v03
docker compose --env-file .env.v03 up --build
```

入口 `http://127.0.0.1:18080`。健康检查 `GET /healthz`。**契约版本：** 0.8.0。**现状日期：** 2026-09-19。

## 技术栈

- 公开 API：Java 21 / Spring（`server/`）
- 执行：Python Engine + Dramatiq（`engine/`）
- 前端：Vue（`web/`）
- 存储：Postgres（`app` / `engine` 分 schema）+ Redis + MinIO
- 契约：`contracts/public-api.yaml`、`contracts/internal-engine-api.yaml`

## 目录与约定

- **现役**：`web/`、`server/`、`engine/`、`contracts/`、`nginx/nginx.v03.conf`
- **Engine 仍依赖**：`models/`、`graph/`、`skill_runtime/`、`skills/`、`retrieval/`；legal profile 链 `agents/`、`audit/`、`config/`、`prompts/`、`storage/`、`tools/`；Compose 挂载 `infra/`
- **边界**：浏览器只打 Java `/v1`，不直连 Engine / MinIO。0.2 遗留树（`apps/`、`domain/`、`migrations/`、`legacy/`、根 `Dockerfile`）已删，engine 侧禁止再 import
- 上传后只轮询 `parseTaskId`，正文只读 `GET /v1/tasks/{id}/result`。不要再创建解析任务，不要传 `storageKey`
- `document.parse` / `model.probe` 必须 Bearer。caseless stub 任务可无会话
- 检索 / 量刑公开口保持 501，直到 T3 会签。`compliance.analyze` / `conviction.analyze` 也保持 501。T3 适配器已在 Engine，Compose 默认开关关闭；只开 Java `SENTENCING_ENABLED` 会建成任务再被 Engine 标 `failed`。不要改公开口或默认开关假装已接通
- DB 只走 Flyway，禁止改已发布迁移。密钥只进 `.env.v03`，禁止提交

## 当前状态（2026-09-19）

- **T1**：案件 / 材料 / 自动解析 / facts / 鉴权 / `model.probe` / 文书草稿空壳 / sentencing facts 门闩 / `ReviewRecord.module` / 合规定罪案件级空壳 / 条级 `verificationStatus` / 草稿改稿 supersede / 无任务开单复核 已在 main；公开检索、量刑、`compliance.analyze`、`conviction.analyze` 默认仍返回 501（分别为 `SOURCE_SEARCH_UNAVAILABLE`、`SENTENCING_UNAVAILABLE`、`COMPLIANCE_UNAVAILABLE`、`CONVICTION_UNAVAILABLE`）
- **T2**：列表 / 新建 / 工作区 / 上传 / facts 已接通（main）。阅卷 / 量刑 / 法源正式页与复核归档已接通并已合入本地 `main`；合规 / 定罪页接 module content，定罪页展示管辖连接点 / 基准位置 / 缺失事项
- **T3**：适配器与 `demo_cases/three_case_demo` 已在 Engine 与镜像（`COPY demo_cases`）；公开检索、量刑、合规与定罪分析入口默认仍按会签门闩返回 501，本地 `.env.v03` 可显式开启
- **演示链路**：本地 `.env.v03` 开双开关 + `scripts/import_three_case_demo.py` 灌三案后，案件中心 → 定罪 → 量刑 → 复核归档可端到端演示；文书字段字典仍待法学会签
- **case-import.v1**：`feat/case-import` 已合入本地 `main`（该分支 tip `5ed75ca` 已是 `main` 的祖先）；租约 fencing 已验证（stale token 不能 claim/complete），ZIP 提取为精确缓冲
- 权威现状：`README.md` 与 `docs/lexcyber-0.8.*.md`。过期时以代码与契约为准

下一步：法学负责人逐案验收 + 文书字段字典会签；并继续完成已合入 import 线的发布验证与评审收尾。产品图与边界见那两份 0.8 文档。
