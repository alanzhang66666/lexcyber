# LexCyber — Agent 规则

可审计任务执行工作台。辅助研判，不替代司法裁量；不产出量刑 / 责任 / 犯罪结论。

## 怎么跑

```powershell
Copy-Item .env.v03.example .env.v03
docker compose --env-file .env.v03 up --build
```

入口 `http://127.0.0.1:18080`。健康检查 `GET /healthz`。契约版本 `0.8.0`。

## 技术栈

- 公开 API：Java 21 / Spring（`server/`）
- 执行：Python Engine + Dramatiq（`engine/`）
- 前端：Vue（`web/`）
- 存储：Postgres（`app` / `engine` 分 schema）+ Redis + MinIO
- 契约：`contracts/public-api.yaml`、`contracts/internal-engine-api.yaml`

## 目录与约定

- **现役**：`web/`、`server/`、`engine/`、`contracts/`、`nginx/nginx.v03.conf`
- **Engine 仍依赖**：`models/`、`graph/`、`skill_runtime/`、`skills/`、`retrieval/`
- **不是公开 API**：`apps/` 是 0.2 Python 面。浏览器只打 Java `/v1`，不直连 Engine / MinIO
- 上传后只轮询 `parseTaskId`，正文只读 `GET /v1/tasks/{id}/result`。不要再创建解析任务，不要传 `storageKey`
- `document.parse` / `model.probe` 必须 Bearer。caseless stub 任务可无会话
- 检索 / 量刑保持 501，直到 T3 会签。不要改 adapter 假装已接通
- DB 只走 Flyway，禁止改已发布迁移。密钥只进 `.env.v03`，禁止提交

## 当前状态（2026-09-14）

- **T1**：案件 / 材料 / 自动解析 / facts / 鉴权 / `model.probe` 已在 `main`
- **T2**：列表 / 新建 / 工作区 / 上传 / facts 已接通。阅卷 / 量刑 / 合规 / 定罪正式页未接通
- **T3**：未做。无 `datasets/`
- 权威现状：`README.md` 与 `docs/lexcyber-0.8.*.md`。过期时以代码与契约为准

下一步：T3 检索会签，或接通正式阅卷 / 量刑页。产品图与边界见那两份 0.8 文档。
