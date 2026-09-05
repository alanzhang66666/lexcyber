# LexCyber v0.3 开发手册

## 本地入口

需要 Docker、JDK 21、Maven 3.9+、Node 22 和 Python 3.12。推荐使用隔离账号版本：

```bash
docker compose -f docker-compose.v03-isolated.yml -f docker-compose.v03-secure.override.yml \
  --project-name lexcyber-v03 up --build
```

浏览器入口固定为 `http://127.0.0.1:18080`。Nginx 只公开静态页面、`/v1/*` 和 `/healthz`；engine、Redis、PostgreSQL、MinIO 不映射宿主机端口。

## 三个工程入口

```text
web/     npm run typecheck && npm run build
server/  mvn test && mvn package
engine/  uvicorn engine.run_api_v03:app --port 8100
```

Java 的 task 写入和 outbox 发布必须在同一事务边界内；engine 的请求必须带 `X-Service-Token`。内部 API 的数据库异常返回明确的 503，不能返回伪造成功结果。

## 测试顺序

```bash
python -m compileall -q engine
pytest -q
cd web && npm run typecheck && npm run build
```

Compose 全链路验收必须使用真实 PostgreSQL、Redis、MinIO、Java 和 Python 服务；Stub 模型只用于显式本地测试配置，不代表真实模型性能。

## 当前安全边界

- 正式身份认证尚未纳入本次骨架；Java 审核变更接口默认 fail-closed，未配置身份提供方时返回 `501`。
- engine 只接收内部服务令牌，不接受浏览器转发的权限列表或 `human_approved` 字段。
- API Key 只能由服务端环境变量提供，禁止写入仓库、前端包或提交历史。
- `engine/migrations` 由独立 Flyway 任务以 `lex_engine` 账号执行；Java 只加载 `db/migration/app`。
