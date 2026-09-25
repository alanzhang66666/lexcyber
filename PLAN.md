# 测试与远端 `main` 直接合入方案

## 摘要

在保留现有 17 个本地提交历史的基础上，整理当前未提交改动，纳入产品源码、测试、文档及 `competition_submission`，完成根系统和比赛目录两套完整单元测试后，直接快进推送至 `origin/main`。本轮不执行 Compose 端到端测试，但任何未通过的单元测试、构建、契约或安全检查都会阻止推送。

## 合入整理

- 先修复 `git diff --check` 报告的文件尾空行和三个部署文件的行尾问题。
- 对 `origin/codex/t1-api01-document-link` 做语义比较，不直接 cherry-pick；当前接口已由本地提交实现，仅移植缺失的契约、smoke 和测试断言。
- 根系统保持 API `0.8.0` 和现有安全门闩，不把比赛目录独有的 `case.assist.analyze`、任务 trace 接口反向复制到根系统。
- 比赛目录作为独立交付线提交，保留其单容器、`case.assist.analyze` 和人工复核链路。
- 将未提交内容拆成三个提交：
  1. `fix(demo): finalize import restore and deployment hygiene`
  2. `feat(web): complete auditable three-case experience`
  3. `chore(submission): add single-container competition delivery`
- 使用显式白名单暂存；允许产品代码、测试、说明文档、比赛目录、ECS 的 README/示例环境文件/启动脚本。
- 明确排除：所有真实 `.env`、`demo-account.env`、`deploy/ecs-upload.tar`、镜像 tar、`deploy/ecs-upload` 内运行数据、原始 `法学材料/`、临时文件、checkpoint、缓存和构建产物。
- 更新忽略规则，确保上述大文件和私有材料以后不会再次进入待提交列表。

## 测试门槛

根系统必须全部通过：

- `python -m ruff check`，根配置排除比赛快照，避免双份源码重复扫描。
- `python -m pytest -q -m "not integration"`。
- `mvn -B test`，工作目录为 `server/`。
- `npm ci`、`npm run typecheck`、`npm test`、`npm run build`，工作目录为 `web/`。
- 校验两份 OpenAPI，并运行 `scripts/check_openapi_snapshot.py`。
- 单独验证三案数据、导入包安全限制、租约 fencing、事件材料回填和量刑重放测试。

比赛目录必须全部通过：

- `tests/acceptance/verify_delivery.py`，确认必需文件、知识库摘要和无缓存/依赖目录。
- Python unit 测试，排除 integration/e2e 外部服务用例。
- 比赛目录内 Java Maven 测试。
- 比赛目录内前端 `npm ci`、类型检查、单测和构建。
- JSON、YAML/OpenAPI、Python 语法及敏感信息扫描。
- 检查无 `.env`、私钥、真实 Token、`node_modules`、`target`、`dist`、缓存和超过 GitHub 限制的大文件。

若 Windows 出现已知的子进程 `WinError 5`，必须在 Linux/WSL 的 Python 3.12 环境复跑相同测试；不能把平台错误直接当作通过。Compose 端到端和真实 DeepSeek 调用不属于本轮推送门槛，但记录为后续发布验收项。

## 推送与验收

- 测试完成后检查 staged diff、提交文件大小、敏感字符串和最终 `git status`；除明确排除的本地材料外，工作区应无待提交代码。
- 推送前再次执行 `git fetch origin`，要求 `origin/main...main` 的远端领先数仍为 `0`；若远端已有新提交，停止推送并重新比较，不自动强推或覆盖。
- 使用普通 `git push origin main:main`，禁止 `--force`。
- 推送后以 `git ls-remote origin refs/heads/main` 验证远端哈希与本地 `HEAD` 完全一致。
- 检查 GitHub CI 已触发；由于本轮未在本地跑 Compose，远端 `compose-e2e` 必须通过才视为最终合入成功。
- 保留 `origin/codex/t1-api01-document-link`，待确认缺失测试已移植后再单独决定是否关闭，不在本轮删除远端分支。

## 假设与停止条件

- 用户已授权直接推送 `main`，但未授权强推、删除远端分支或上传原始法学材料。
- 法学会签暂不可用，因此检索、量刑、合规和定罪公开安全门闩保持现状。
- 任一测试、构建、契约、秘密扫描或远端 CI 失败即停止合入；只修复失败原因，不降低测试门槛。
- 远端成功标准是：目标文件完整、无敏感或超大文件、远端 `main` 等于本地 `HEAD`、所有 GitHub CI 作业通过。
