# T1 检索与 embedding 边界（待 T3 会签）

本轮不实现法规切分、向量入库或真实检索。公开路径已经留好，T3 只改 adapter。

## 入口

- 浏览器只调用 Java `POST /v1/sources/search`。
- Java 只调用 Engine `POST /internal/v1/sources/search`（`X-Service-Token`）。
- Engine 只调用 `engine/adapters/sources.py`。当前未接通时返回 `501 SOURCE_SEARCH_UNAVAILABLE`。
- 禁止把 [`retrieval/corpus.py`](../retrieval/corpus.py) 的样例条文当作公开结果。

## 所有权

| 事项 | 负责 |
| --- | --- |
| Compose、密钥、schema 权限 | T1 |
| `index_legal_sources()` / `search_legal_sources()`、切分格式、入库脚本 | T3 |
| 公开 DTO | `contracts/public-api.yaml` |

浏览器和 Java 都不直连向量库。

## T1 建议（T3 可驳）

1. 沿用现有 Postgres，增加 `retrieval` schema 和 pgvector。
2. embedding 使用与模型相同的 OpenAI-compatible 基座：`EMBEDDING_PROVIDER`、`EMBEDDING_MODEL`、`EMBEDDING_API_KEY`。
3. 备选：外置知识库走已有 `KNOWLEDGE_BASE_URL`（[`retrieval/gateway.py`](../retrieval/gateway.py)），仍只从 Engine adapter 进入。

未会签前，Compose 不新起独立向量容器。变量已写在 `.env.v03.example`，默认可空。

## 会签状态

- **T3 会签：pending**（2026-09-08）
- 本轮不把「同意 / 驳回备选」写成已完成。T3 会签前不增加向量容器。
