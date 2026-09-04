# Lex Multi-Agent Backend v0.2

一个可运行的多智能体后端，带有可注册、可选择、可执行、可审计、可人工复核的法律 Skill Runtime。

本版本重点完成：

> Skill 可注册、可选择、可执行、可审计、可引用法源、可人工复核。

当前版本提供：

- FastAPI API Gateway：任务、案件、文档、Skill、人工审核
- LangGraph 工作流：Normalize → Case Context → Supervisor → Skill Router → Policy Gate → Skill Executor → Merge → Reviewer → Human Review / Output
- Skill Runtime：JSON Schema 校验、权限、超时、错误码、幂等、执行审计
- Legal Skill Pack v0.2：22 个基础 Skill（10 个升级 + 12 个新增）
- PostgreSQL：任务、checkpoint、Skill Registry、案件/文档/证据、人工审核、Audit
- Redis + Dramatiq 异步任务队列
- MinIO 对象存储
- Retrieval Gateway：私有知识库契约 + 本地法源样例语料
- GitHub Actions：Ruff、Pytest、Compose 配置校验

本版本不包含定罪、责任认定、案件结果预测等法律结论能力。

## 目标工作流

```text
用户任务 → Supervisor 制订计划 → Skill Router 选择 Skill
→ Policy Gate 权限与风险检查 → Skill Executor 执行
→ 结果写入 AgentState → Reviewer 审核
→ PASS 生成结果 / RETRY 重试 / NEED_HUMAN 进入人工审核队列
```

## 快速启动

```bash
cp .env.example .env
docker compose up --build
```

API 默认入口：`http://localhost:8080`

```bash
curl http://localhost:8080/healthz

curl -X POST http://localhost:8080/v1/tasks \
  -H 'Content-Type: application/json' \
  -d '{"query":"提取合同付款条款","metadata":{"text":"第一条 付款。甲方应于2024年1月1日支付人民币10000元。","jurisdiction":"CN"}}'
```

## 主要 API

```text
POST   /v1/tasks
GET    /v1/tasks/{task_id}

GET    /v1/skills
GET    /v1/skills/{skill_id}
POST   /v1/skills/{skill_id}/execute
GET    /v1/skill-executions/{execution_id}

POST   /v1/cases
GET    /v1/cases/{case_id}
POST   /v1/cases/{case_id}/tasks
POST   /v1/cases/{case_id}/documents
GET    /v1/documents/{document_id}
POST   /v1/documents/{document_id}/parse
GET    /v1/documents/{document_id}/content

GET    /v1/reviews
GET    /v1/reviews/{review_id}
POST   /v1/reviews/{review_id}/approve
POST   /v1/reviews/{review_id}/reject
POST   /v1/reviews/{review_id}/request-retry
```

Nginx 只暴露统一 API，不直接对外暴露 PostgreSQL、Redis、MinIO 和内部 Gateway。

## 本地测试

```bash
pip install -e ".[dev]"
pytest -q
```

## 目录结构

```text
lexcyber/
├── apps/                  # API、Worker、Model/Retrieval/Skill Gateway
├── agents/                # Supervisor、Worker、Tool、Reviewer
├── graph/                 # LangGraph state、nodes、routing、workflow
├── domain/                # 案件、文档、证据、人工审核
├── models/                # Model Gateway
├── retrieval/             # Retrieval Gateway 与本地法源样例
├── tools/                 # Tool Gateway
├── storage/               # PostgreSQL、Redis、MinIO
├── audit/                 # Agent Audit Log
├── skills/                # Skill catalog 与 handler
├── skill_runtime/         # Registry、Router、Policy、Executor、Validator
├── migrations/            # PostgreSQL SQL 迁移
└── tests/                 # 单元、集成、端到端测试
```

## 安全边界

- Skill 只能从 `skills/catalog.json` 加载，不能执行未注册入口。
- 高风险法律行为默认进入人工审核，禁止自动化提交法院或签署文件。
- 引用验证只是检索匹配，不是权威法源真实性证明。
- 模型 API Key 只从环境变量读取，不写入仓库。
