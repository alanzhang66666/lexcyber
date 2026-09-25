# LexCyber 比赛交付版：案件材料辅助研判智能体

本目录是比赛提交物的第 1 文件夹，包含可运行的完整源码、运行必需的提示词与本地知识资源、测试、演示输入和单容器启动文件。它不依赖仓库外的源码，也不包含任何真实 API Key。

提交要求与文件位置的逐项映射见 `SUBMISSION_MANIFEST.md`，构建和运行依赖见 `DEPENDENCIES.md`。

## 运行形态

评审环境只需要 Docker。容器内部启动 Java 公共 API、Python Engine、Worker、PostgreSQL、Redis 和 Nginx；浏览器只访问 Nginx 暴露的端口。运行时唯一允许的外部服务是配置的 DeepSeek 兼容 API。

```text
浏览器 → Nginx → Java API → PostgreSQL / 本地对象存储
                         → Python Engine → Redis/Worker
                                         → 本地知识库 → DeepSeek 兼容 API
```

## 构建与启动

```powershell
Copy-Item .env.example .env
# 编辑 .env，至少替换数据库口令、服务令牌与 MODEL_CONFIG_ENCRYPTION_KEY

docker build -t lexcyber-competition .
docker run --name lexcyber-competition `
  --publish 18080:8080 `
  --env-file .env `
  --volume lexcyber-competition-data:/data `
  lexcyber-competition
```

打开 <http://127.0.0.1:18080>。首次进入后注册本地账号，在「用户设置 → 模型 API 接入」填写供应商、模型名、API Base URL、API Key 与超时秒数；API Key 会加密保存且不会回显。随后可创建案件并上传 `examples/` 中标记为演示输入的 PDF/DOCX。健康检查：

```powershell
curl.exe http://127.0.0.1:18080/healthz
```

停止和重新启动容器不会丢失 `/data` 中的案件、任务、结果和审计记录：

```powershell
docker stop lexcyber-competition
docker start lexcyber-competition
```

## 可复核任务链

案件材料上传后，网页按以下顺序展示真实执行过程：文档解析与定位 → 事实/主体/时间线抽取 → 本地法源检索 → DeepSeek 结构化分析 → 引用和事实支持校核 → 结构化结果 → 人工复核。每个任务都有任务编号、执行编号、阶段、工具/知识调用、异常、耗时和模型 Token/延迟统计。

结果是辅助研判材料，不替代司法裁量，不自动输出犯罪、责任或量刑结论。缺失材料、法源未命中、引用无法验证或模型调用超限时，任务会被阻断或标记失败，并进入人工复核。

## 模型配置

模型接入参数已纳入登录后的用户设置。模型名仍是配置项，因为 DeepSeek 的正式模型名以组委会最终通知和官方 API 实际可用名称为准。默认示例使用 `deepseek-v4-flash`，不代表该名称已经被平台确认。`MODEL_CONFIG_ENCRYPTION_KEY` 用于服务端 AES-GCM 密文存储，运行后不要随意更换；环境变量中的 `MODEL_*` 仍作为数据库尚无保存记录时的回退值。

正式运行禁止 stub 回退。未配置 Key、请求超时、模型返回非法结构或超过调用预算时，不会伪造成功结果。详见 `.env.example` 和 `DEPENDENCIES.md`。

## 测试

```powershell
python -m pytest -q tests/python
npm --prefix src/web ci
npm --prefix src/web run build
mvn -f src/server/pom.xml -B test
```

容器验收还必须在干净目录执行一次 `docker build`、`docker run`、网页成功任务和边界任务。测试输入位于 `examples/`，明确标注为“演示输入，非智能体组成部分”。

## 文件和凭据边界

- `.env` 只在评审机上创建，禁止提交；`.env.example` 只有占位符。
- `knowledge/` 中的材料必须有来源、版本、发布日期、生效范围、获取日期和 SHA-256 台账。
- `examples/` 只保存可公开演示输入，不作为法源或模型规则本身。
- 运行结果、原文和审计数据全部保存在 Docker volume `/data`，不会写入源码目录。
