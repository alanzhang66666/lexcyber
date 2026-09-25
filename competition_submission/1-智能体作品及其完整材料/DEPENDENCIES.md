# 依赖清单

## 评审机要求

- Docker Engine 24 或更高版本，能够构建和运行 Linux/amd64 容器；
- 首次构建时可访问系统包、Maven、npm 与 PyPI 软件源；
- 可访问配置的 OpenAI-compatible 模型 API，只有真实模型调用需要该网络出口；
- 浏览器用于访问 `http://127.0.0.1:18080`。

评审机不需要预装 Java、Node.js、Python、PostgreSQL、Redis、Maven 或 npm。

## 构建与运行环境

| 用途 | 镜像或组件 | 版本/约束 |
| --- | --- | --- |
| Java 构建 | `maven:3.9.9-eclipse-temurin-21` | Maven 3.9.9、Java 21 |
| 前端构建 | `node:22-bookworm` | Node.js 22 |
| Python 构建 | `python:3.12-slim-bookworm` | Python 3.12 |
| 最终运行镜像 | `ubuntu:24.04` | Ubuntu 24.04 |
| 应用运行时 | OpenJDK、Python、PostgreSQL、Redis、Nginx、Supervisor | 由 `Dockerfile` 在 Ubuntu 24.04 软件源安装 |
| 数据库迁移 | Flyway Commandline | 10.20.1 |

基础镜像、安装步骤和 Flyway 下载地址以根目录 `Dockerfile` 为准。

## 应用依赖的权威清单

- Python 运行依赖及版本范围：`src/pyproject.toml`；开发/测试依赖位于其中的 `dev` extra。
- Java 依赖及插件：`src/server/pom.xml`，父 BOM 为 Spring Boot 3.3.5。
- 前端直接依赖：`src/web/package.json`；完整传递依赖和校验值锁定在 `src/web/package-lock.json`。
- 系统级依赖、构建镜像和复制边界：根目录 `Dockerfile`。

主要运行组件包括 Spring Boot、PostgreSQL JDBC/Flyway、FastAPI、Dramatiq/Redis、LangGraph、Pydantic、HTTPX、文档解析组件、Vue 和 Vue Router。许可证归各上游项目所有，组件范围说明见 `THIRD_PARTY_NOTICES.md`。

## 外部服务与本地数据

- 模型服务是唯一需要运行者提供凭据的外部服务；参数可在 `.env` 中提供，也可登录后在“用户设置 → 模型 API 接入”中密文保存。
- PostgreSQL、Redis、对象文件、本地法源索引和提示词均包含在单容器运行边界内。
- `.env.example` 只含占位值，不含真实凭据；`MODEL_CONFIG_ENCRYPTION_KEY` 在首次正式运行前必须替换，后续不可随意变更。
