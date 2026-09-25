# 提交材料清单

本目录对应提交要求“可运行的智能体作品及其完整材料”。评审者只需 Docker，即可从本目录独立构建和启动，不依赖仓库其他目录。

| 要求 | 随附材料 | 位置 |
| --- | --- | --- |
| 完整源代码 | Java 公共 API、Python Engine/Worker、Vue 前端、共享智能体与技能运行时代码 | `src/server/`、`src/engine/`、`src/web/`、`src/agents/`、`src/skills/` 等 |
| 接口与数据结构 | 公开/内部 OpenAPI、导入包及协作数据 JSON Schema、数据库迁移 | `src/contracts/`、`src/server/src/main/resources/db/migration/`、`src/engine/migrations/` |
| 必要本地资源 | 版本化提示词、本地演示法源索引、演示与边界输入 | `prompts/`、`knowledge/`、`examples/` |
| 依赖清单 | 构建/运行环境、依赖入口及版本约束 | `DEPENDENCIES.md`、`src/pyproject.toml`、`src/server/pom.xml`、`src/web/package-lock.json` |
| 配置示例 | 无真实密钥的完整环境变量模板 | `.env.example` |
| 安装与启动说明 | 单容器构建、启动、健康检查、停止和重启 | `README.md` |
| 容器编排材料 | 多阶段构建、进程入口、Nginx 与 Supervisor 配置 | `Dockerfile`、`container/` |
| 测试与验收 | Python/Java/前端测试及交付自检、最近一次验证记录 | `tests/`、`tests/acceptance/VERIFICATION.md` |
| 第三方与资源说明 | 第三方组件说明、知识资源来源与覆盖边界 | `THIRD_PARTY_NOTICES.md`、`knowledge/PROVENANCE.md` |

## 不应出现在提交包中的内容

- `.env`、真实 API Key、访问令牌或账号密码；
- `node_modules/`、`target/`、`dist/`、缓存和运行日志；
- PostgreSQL、Redis、上传原文或运行结果；这些数据只写入运行时 Docker volume `/data`；
- 未授权的完整法律数据库或真实案件材料。

## 提交前自检

在本目录执行：

```powershell
python tests/acceptance/verify_delivery.py
docker build -t lexcyber-competition .
```

自检脚本检查必要文件、生成物残留和常见密钥格式；镜像构建同时编译 Java、Vue 和 Python 包。运行步骤及预期健康检查见 `README.md`。
