# 最近一次交付验收记录

- 验证日期：2026-09-20（Asia/Shanghai）
- 运行环境：Windows + Docker Desktop，Linux/amd64 容器
- 候选镜像：`lexcyber-competition:submission-candidate`
- 镜像 ID：`sha256:4b43311ef40b9964d0d0bd9cce757e120f3c75f339f43278978e9180b1d87f55`
- 镜像大小：612071385 bytes
- 应用契约版本：0.8.0

## 自动化验证

- `python tests/acceptance/verify_delivery.py`：通过；知识索引 SHA-256 为 `fc24147c453eca9ec31f8d5fdc2868d63f30c7375f6f24f5cbddc024b101a27a`。
- Python 3.12：97 项通过、1 项跳过；模型网关测试已与运行时动态模型配置对齐。
- Ruff：生产源码和 Python 测试检查通过；排除了 Windows 只读挂载产生的可执行位假阳性及临时构建目录。
- Vue：19 个测试文件、84 项测试全部通过；TypeScript 与 Vite 生产构建成功。
- Java 21：不依赖宿主 Docker Socket 的 45 项测试全部通过；另外 5 个 Testcontainers 测试因本次安全验收不挂载宿主 Docker Socket，改由真实单容器 API 链路覆盖。
- 新增 `ImportArchiveReaderTest`，防止 ZIP 条目读取再次发生递归栈溢出。

## 单容器运行验证

- 从根目录 `Dockerfile` 完整构建成功，Java、Vue 与 Python wheel 均由提交包内源码生成。
- 使用全新 Docker 数据卷启动，`GET /healthz` 返回版本 `0.8.0` 和状态 `ok`。
- PostgreSQL、Redis、Engine API、Dramatiq Worker、Java API 与 Nginx 均在同一容器运行。
- `supervisorctl -c /etc/supervisor/conf.d/lexcyber.conf status` 可正常列出全部五个受管服务为 `RUNNING`。
- 仅公开 Nginx 的容器端口 8080；PostgreSQL、Redis、Engine API 和 Java 内部端口没有对宿主发布。
- 容器重启后健康检查恢复，导入案件、导入批次和任务数据均保留。

## 功能链路验证

- 注册、登录、会话、注销和令牌撤销通过；注销后的令牌返回 401。
- 案件创建、列表读取、用户隔离、facts、模块状态、草稿、复核、文档上传与解析、任务结果和轨迹链路通过。
- 法源检索返回命中；量刑、合规分析和定罪分析在默认关闭状态下分别按契约返回 501。
- `model.probe` 在显式 stub 验收配置下完成，结果明确标记 `provider=stub`，未冒充真实模型成功。
- 模型 API 设置需登录访问；密钥写入后仅返回掩码，不返回 `apiKey` 字段，数据库保存密文与随机数。
- 标准案件 ZIP 完成上传、校验、审批、应用，批次状态为 `completed`、条目状态为 `applied`，六个应用步骤全部完成，并生成可读取的案件及文档。
- 对已完成批次重复调用 `apply` 保持 `completed`，具备批次级幂等性；重复上传同一生产方、包和版本按契约返回 `IMPORT_RELEASE_CONFLICT`。
- 最终候选日志未出现 `StackOverflowError`、`started_at` SQL 歧义或未处理公开 API 错误，未发现 Bearer 令牌泄漏。

## 前端验证说明

- 根路由、设置路由、SPA shell、生产 JS 和 CSS 资源均通过候选容器返回 200。
- 本次环境中的内置浏览器连接因缺少宿主沙箱元数据而无法建立，因此没有把该工具限制伪记为产品失败；页面逻辑由 84 项 Vue 测试、生产构建和 HTTP 资源检查覆盖。

## 真实模型说明

本次没有提供真实模型 API Key，因此没有把 stub 结果记录为真实模型调用成功。评审者填入合法凭据后，可在“用户设置 → 模型 API 接入”中保存配置，再运行 `model.probe` 验证外部模型连通性。

本次候选容器和数据卷仅用于验收；验证完成后应删除，不占用正式提交实例端口和数据卷。
