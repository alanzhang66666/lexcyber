# v0.2 -> 0.8 迁移清单

- [ ] 新环境使用 Compose project `lexcyber-v03`（历史工程名），入口 `127.0.0.1:18080`。产品版本为 **0.8**。
- [ ] 根目录 `docker-compose.yml` 是当前默认配置；`legacy/docker-compose.v02.yml` 仅归档，不再维护。
- [ ] 新库采用 `app` 与 `engine` schema，分别使用独立数据库账号。
- [ ] Flyway 是唯一建表/迁移入口；Python 启动时不执行建表 SQL。
- [ ] Java 不写 `engine` 表；Python 不读写 `app` 业务表。
- [ ] 旧测试数据卷不迁移；旧环境保持只读归档。
- [ ] 22 个已注册 Skill 的 id/version/handler 与行为契约逐一盘点。
- [ ] 移除 Worker 内存审计与虚假 review id；所有执行、产物和审计都有持久化记录。
- [ ] PDF 页码、DOCX 段落和表格使用独立 locator；解析失败必须返回失败状态。
- [ ] 真实模型 API 只通过 Python `ModelGateway` 调用；自动化测试使用显式 Stub。
- [ ] Worker 强制终止、租约失效和重试场景各保留一份集成报告。
- [ ] Compose 校验、OpenAPI 漂移检查、Java 测试、Python Ruff/Pytest、Vue build 全部通过后再推送。
