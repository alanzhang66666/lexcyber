# Lex Multi-Agent Backend v0.1

一个不包含法学判断节点的、可运行且可扩展的多模型 Agent 后端骨架。

当前版本提供：

- FastAPI API Gateway
- LangGraph 工作流：Input Normalize → Supervisor → Worker/Tool → Reviewer → Output
- 通用 Supervisor、Worker、Tool、Reviewer 四类 Agent
- Model Gateway + Model Router，支持主模型/备用模型接口
- Retrieval Gateway，隔离现有私有知识库
- PostgreSQL 工作流状态、checkpoint、Prompt Registry、Audit Log
- Redis + Dramatiq 异步任务队列
- MinIO 对象存储基础设施
- Docker Compose 部署和 Nginx 入口

本版本不包含罪名、涉外、证据或其他法律判断节点。未来业务 Agent 只需新增节点和 prompt，不需要重构基础设施。

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
  -d '{"query":"总结这段输入并返回结构化结果"}'
```

返回的 `task_id` 可用于查询：

```bash
curl http://localhost:8080/v1/tasks/<task_id>
```

没有配置模型 API Key 时，Model Gateway 会使用明确标记的 deterministic stub，方便先跑通架构；接入真实模型时只需配置 `.env`。

## 目录结构

```text
lex-backend/
├── apps/                  # API、Worker、Model/Retrieval Gateway 服务
├── agents/                # 四类通用 Agent
├── graph/                 # LangGraph state、nodes、routing、workflow
├── models/                # Model Gateway、Router、schemas
├── retrieval/             # Retrieval Gateway client、schemas
├── tools/                 # Tool Gateway
├── storage/               # PostgreSQL、Redis、MinIO 适配层
├── audit/                 # Audit Log
├── config/                # 配置
├── prompts/               # Prompt Registry
├── migrations/            # PostgreSQL 初始化 SQL
├── nginx/                 # 统一入口
└── tests/                 # 最小工作流测试
```

## 后续扩展点

1. 在 `models/router.py` 增加供应商和模型路由，不让 Graph 节点直接依赖具体 SDK。
2. 在 `retrieval_gateway` 接入现有私有库，保持 `/retrieval/search` 契约不变。
3. 在 `agents/` 增加领域 Agent，并通过 `graph/routing.py` 插入节点。
4. 用真实 LangGraph checkpointer 替换当前 PostgreSQL checkpoint adapter。
5. 为 `audit.events` 接入 OpenTelemetry、Prometheus 和集中式日志。

## 安全边界

- 默认不上传文件、不调用外部知识库、不执行任意代码。
- 工具调用必须经过 `ToolGateway`。
- 模型 API Key 只从环境变量读取，不写入仓库。
- `.env`、密钥、运行时文件和本地数据均被 `.gitignore` 忽略。
