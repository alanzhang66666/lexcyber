# 人工智能大赛校赛版 · LexCyber Campus Lite

> 独立 JoyCode / JD DevCloud 演示子项目；**不修改原 LexCyber Java/Python/Vue/Postgres/MinIO 全栈系统**。
> 本目录围绕上传的三份校赛 Word 所定义的金融方向 F1/F2/F3 演示，而不是司法帮信罪生产系统。

## 功能
- F1 企业准入、F2 异常交易，使用**合成事实及演示规则**（8 条，不是监管法定标准）。
- 工作副本事实编辑、不可变 FactsVersion 确认；确认新版自动使旧 Artifact stale。
- 逐规则结果和条件 Trace、人工批准/退回、HTML 审查报告/打印。
- 三个**固定问题**的可追溯 Agent 解释（无需外部 LLM）；单页移动端适配。
- 演示动作日志；非正式合规批准、非司法决定。

## 启动（只占一个 8080 端口）
需要 Node.js 20+：
```sh
cd 人工智能大赛校赛版
npm install
npm test
PORT=8080 npm start
```
访问 http://localhost:8080 ，健康检查 `/healthz`。

### JoyCode 部署
在 JoyCode 选择**本目录作为项目根**、Node.js 运行时，执行 `npm install`，启动命令 `npm start`，配置端口 `8080`（或依托支持 Dockerfile 的部署方案）。若平台只能识别 Git 根目录，则将本目录独立导出作为部署仓库/项目，**不要以 LexCyber 主仓库根目录直接检测 Node.js**。

**推荐正式演示环境使用 MySQL**：平台创建 MySQL 实例，并将连接 URL 作为 Secret `DATABASE_URL=mysql://user:password@host:3306/database` 注入；服务自动创建 `campus_lite_state` 单表并初始化合成数据。数据库用户需要该表的 CREATE/SELECT/INSERT/UPDATE 权限。可选 `DB_SSL=true`（视服务端 TLS 要求而定）。不能把连接凭据写入仓库、PPT 或截图。

若未配置 DATABASE_URL，自动进入 `demo-memory` 预览模式：**重启即丢失演示编辑、复核及版本记录，不能作为持久演示验收**。正式线上演示应检查 `/healthz` 返回 storage=mysql。

## 测试/验收
```sh
npm test
curl http://127.0.0.1:8080/healthz
```
人工 E2E：F1 确认→运行→查看缺字段阻断→退回→修改事实并确认→旧结果 stale→再运行；F2 确认→运行→查看多规则 Trace→退回；Agent 三个问题均返回事实/工件版本。F1 与 F2 规则按演示场景隔离，不适用规则显示 not_applicable，适用规则缺少输入显示 blocked；正式业务仍需法律或合规专业人员验证规则口径。当前为校赛演示版，不声称符合正式金融机构复核标准。

## 与原主系统关系
| 原系统 | 校赛版 |
|---|---|
| Vue / Java / Python Engine 多服务 | 单 Node.js + 内嵌静态 HTML 界面 |
| PostgreSQL, Redis, MinIO | MySQL 可选（推荐正式演示），无 Redis/MinIO |
| Legal Pack / Finance Pack 语料治理 | 8 条隔离的合成演示规则，不导入已会签法源 |
| 严格 CAS、不可变工件与正式审计 | 简化版本闭环；**不提供真实司法/金融审计保证** |

校赛版与完整 LexCyber 之间**不共享数据库或业务状态**，结果不互相导入，也不替代原系统的法学签署或权限模型。部署前仅使用合成数据；当前页面无登录鉴权，必须放在受控演示环境，**禁止传入真实用户、客户或司法卷宗**。

## Word 对应
- 选题说明：Finance Compliance Pack、F1 企业准入、F2 异常交易、F3 stale。
- 系统说明书：最小改造、独立演示、测试闭环、人工复核。
- PPT 脚本：规则 Trace、可视化事实确认、解释对话和 3 个可操作问题。

后续：生产环境会话鉴权/权限、规则适用域、正式法源追溯、真实文件处理、评测、MySQL 数据表规范化和正式人工审查流程。
