# LexCyber 架构演进 Roadmap（v1.3 实施）

> 本文件承载 v1.3 §0.2 明确排除出架构书的「交付状态 / 阶段 / 进度」内容。
> 目标架构唯一权威：`LexCyber-system-architecture-v1.3-postgresql-physical-model.md`。
> 矛盾裁决：`docs/adr/ADR-0001` ~ `ADR-0006`。

## 基线

- 冻结点 tag：`arch-v13-baseline`（main `a078dea`）
- `competition_submission/`、`本科生组+…/`：冻结快照，不再与主树同步
- `/v1` 契约：冻结为读取兼容层；新生命周期端点走 `/v2`

## 2026-10-08 main 修复验证（进行中）

审核基线为 `8aadc846174436f88b5ab388e3c5a5d1fe755e01`。该提交 CI 五项全通过，但遗漏了文书批准、旧 execution 迟到发布、渲染输入依赖竞态及多规则量刑阻断展示。

最近完整验收提交 `dd61e5b7df67df8f1216da5fd6ec2326947f13ee` 的 [CI 37693953565](https://github.com/alanzhang66666/lexcyber/actions/runs/37693953565) 五个 job 全部成功：Java/Postgres 141 项，0 失败/错误/跳过（包含 V21→V22 带数据升级）；Python 非 integration 224 项；web 126 项、实际 Vue 页面类型检查及生产构建；三个 OpenAPI。Compose 16 项业务检查、§19 三项实际并发、注册表数据库 12 项均通过，含缺失日期阻断、日期 CAS、旧日期批准拒绝和历史指针保留。该结果证明此提交的已测行为，后续新增修复仍须独立验收；PR #15 仍为 draft，main 未合入。

- 修复分支 `codex/repair-main-lifecycle`：渲染文书使用 UUID 描述符与 head；V21 前向迁移保留旧流及历史版本，将不可验证的旧待审稿关闭为 superseded，要求重新生成。
- 派发冻结有效已确认模块的 payload 和 artifact version ID；渲染回调仅绑定实际输入版本，审批再次校验事实与模块依赖。未会签能力继续 fail-closed。
- 旧 execution 不发布；失败回调不发布；回调重放不新建复核或回退已完成执行。复核决策校验请求版本。
- 前端整体 blocked 不输出刑期，各规则结果可追溯；开发服务器同时代理 `/v1` 和 `/v2`；任务轮询隔离旧路由响应。
- 事实工作副本新增历史、diff 和版本回写入口；切案后清理旧编辑及请求，工作副本与已确认快照比对后再显示确认状态。事实写入使用契约中的复数实体路径。复核详情改用案件归档，展示固化的 manifest，不再调用退役的单条复核归档。
- 空案件归档返回可定位的事实缺口；未知 archive profile 拒绝。归档创建与读取使用一致的公开字段。v2 模块/文书派发响应状态与公开契约一致。v2 任务重试重验能力、保留冻结输入，依赖变更后要求重新派发；不能混用旧快照与新事实引用。
- v2 OpenAPI 响应补齐必需描述并接入合同 CI。Compose 验证使用明确标注的隔离 CI 规则/模板，实际驱动模块、文书、批准和归档；§19 检查要求确认、回调重放及复核/归档并发，必需检查 SKIP 不再算验收成功。测试 fixture 不构成正式法学批准。
- 续查归档：按照权威 §5.11 强制要求三个有效模块与批准文书，不能仅有 facts 就创建完整归档；已有过期文书继续阻断。同一 manifest 在案件行锁内复用原归档，不增加版本号。并发脚本使用完整四工件 fixture，注册表 8 项数据库集成测试接入迁移后的 Compose 环境，数据库不可达即失败。
- 提交 `3adfe52` 的 CI `37670947026`：Python、web、contracts 成功；Java 107 项中 1 错误，重复归档触发 manifest 唯一约束；Compose 因此前置失败未运行。本次补丁修复该真实错误，不通过删约束或放宽测试绕过。
- 提交 `829a6bc` 的 CI `37673310917` 五个 job 成功：Java/Postgres 110 项、0 跳过；Python 166 项非 integration、前端 110 项；完整 Compose 生命周期、§19 三项实际并发检查与注册表 8 项真实数据库测试通过。`8cb7de5` 曾暴露重复归档响应的顺序/类型不一致，已统一响应并保留等价性测试。
- 续查量刑管道：INV-PIPE-001 要求有效定罪后才派发量刑，派发冻结精确定罪 ID，发布保留历史依赖，批准重验当前有效上游；量刑重试也必须校验原依赖。执行期间上游变化不会使真实完成回调无限 409 重试，而是保存旧依赖结果、拒绝后续确认。本地 Python 167 项、Ruff、Java test-compile 通过，新增数据库用例待 CI 验证。
- 提交 `74b1aef` 的 CI `37674521616` 五个 job 成功：Java/Postgres 112 项、0 跳过；Python 167 项、web 110 项；完整 Compose/§19 与注册表 8 项数据库测试再次通过，包含量刑派发、迟到回调历史依赖和重试失效检查。
- 归档清单进一步改为从核心工件沿正规化依赖表递归取 parse/supporting 历史版本，排除无关解析流的 latest；保持同案门闩与幂等。本次仅冻结已登记的显式依赖，不推测未记录的事实来源边。
- 提交 `d4cedb5` 的 CI `37675896176` 五个 job 成功：Java/Postgres 114 项、0 跳过；Python 167 项、web 110 项；完整 Compose/§19 与注册表 8 项数据库测试通过，新增递归历史解析依赖、多层 supporting 和跨案依赖阻断用例均已执行。
- 文书下载实现：Java `/v2/cases/{caseId}/artifact-versions/{artifactVersionId}/export.docx` 校验属主、案件与精确工件版本，Engine 内部格式化器生成真实可编辑 DOCX，Java 经 MinIO 存储回读并校验。支持 `draft.v2` 和手工 `case.draft.v1`；blocked、空正文及未替换占位符禁止导出；历史/stale 版本仍可读取辅助稿，不改变工件、批准或归档状态。前端提供下载及切案请求隔离。新增真实 Compose 下载、中文内容、重复字节、历史版本和权限拒绝验收纳入本提交 CI；本节不提前宣称新提交 CI 已通过。
- 本地 DOCX 修复验证：Python 非 integration 179 项、前端 122 项、Vue 类型检查与生产构建、三个 OpenAPI 均通过；Java 导出 client 4 项通过，数据库用例已编译待 CI 实跑。实际生成两页中文 DOCX，检查全部分页图片并确认正文逐字符相等（换行统一为 LF），包括制表符、空行和末尾换行。首轮发现 Title 默认蓝色边框并已移除；本机渲染器补充系统中文字体路径后完成视觉验收，未修改用户字体安装。
- 提交 `1000103` 的 CI `37682223967`：Java/Postgres 123 项、Python 179 项、web 122 项与三个 OpenAPI 成功；Compose 首次 DOCX 下载失败，后续 §19/注册表步骤未执行。原因已复现：自定义 JDK 客户端默认 h2c 升级导致 Uvicorn 接收不到请求正文（422），DOCX Accept 下错误响应再因媒体协商变成 500。修复为 HTTP/1.1、显式 JSON 请求与 JSON 错误响应；用实际 Java 客户端→FastAPI 验证中文 DOCX 和两次字节一致，31 项 HTTP/client 回归通过。当前补丁的完整 Compose 验收仍以新提交 CI 为准。
- 补齐架构 §9.4 的管辖门槛：定罪只认可不可变事实快照中 `jurisdictionConnections[].verificationStatus=confirmed`，缺失/候选/拒绝/未知状态输出定位明确的 blocked 结果；不改变合规行为，也不推定合规适用性。Python 非 integration 187 项与 Ruff 通过；新增真实 Compose 的空连接点、candidate 结果及批准阻断检查，待新提交运行。
- 提交 `e875d8d` 的 CI `37685380267` 五个 job 全部通过：Java/Postgres 128 项、0 跳过；Python 187 项；web 122 项；三个 OpenAPI；真实 DOCX 存储/下载、历史版本与权限、完整生命周期、缺失/candidate 管辖阻断、§19 三项并发和注册表数据库 8 项均执行成功。
- 续查 INV-DATA-001 发现金额总项与组成部分重复累计，120000 + 其中 80000 被错误聚合为 200000、误触发仓库谓词。修复按 kind 分组、按各聚合的有效数字与确认状态沿 componentOf 去重；不同口径保持独立，候选总项不吞掉已确认子项。支持真实 Java 快照 entityId UUID 与外部 id 别名。无效/循环图和非有限值以明确不可重试错误关闭执行，不输出可批准的数字。工作副本金额引用在删除前验证，未知/跨案/自引用/循环/重复身份拒绝，合法 UUID 关系可读回再保存。entityId 仅作本次输入图别名，父引用只写入新建同案节点；补测不可变历史快照连续两次相同 PUT，避免第一次替换删除原 UUID 后第二次报 400。Python 205 项、Ruff、Java test-compile 通过；新增真实 Compose 金额规则追溯、UUID 读写和拒绝后原数据保留，以及数据库校验用例，完整验证待本次提交 CI。


- 规则/模板正式会签、B/C 映射和量刑基准校正仍按法学待签清单办理，不能由代码修复代替。
- 移除已失效的旧 `tests/integration/test_registry.py`：该测试依赖已删除的根 `migrations/` 与 `skill.*` schema，并把任何错误都转为 skip。现役技能目录读取已有 `test_skill_runtime.py` 覆盖，真实 Engine V6 注册表继续执行 8 项数据库集成测试。历史 `storage/postgres` 代码保留供非 Engine 遗留路径使用；本次不恢复旧 schema，也不把旧技能目录错映射到法学规则包。

本节记录进行中的工作，不替代下面的历史实测，也不证明全部功能已完成验证。

- 续查 INV-LEGAL-002：v2 派发未绑定 `cases.as_of_date`，`active_rules` 实际回退到数据库当天日期；同一任务跨日可选不同规则。现冻结 `metadata.asOfDate` 与输入哈希/outbox，Engine 严格解析并传参，删除 `current_date`/检索 `date.today()` 回退；输出依赖记录日期。缺失/无效日期明确阻断且不可重试。案例既有未填日期可通过带 expected-date CAS 的 `/v2/cases/{id}/analysis-date` 补填；变更保留历史与批准指针、使模块/文书失效。确认/批准持案件锁后重验日期，旧日期完成保存历史但不可批准；V22 前向迁移使历史未绑定日期的 v2 确认/批准失效。未改已应用迁移或法学规则。
- 日期修复本地 Python 224 项、Ruff、前端 126 项及实际 Vue 页面类型检查、TypeScript/Vite build、三个 OpenAPI 通过；Java test-compile 通过，新增数据库/真实 Compose 日期拒绝、CAS、依赖追溯与旧日期批准拒绝，以及 12 项注册表数据库检查，待本次提交完整 CI。
- 日期验收负面记录：`4204f5a` 的 CI 暴露新失效原因未纳入数据库 CHECK，以及重试夹具漏填日期依赖；修正 V22 在失效旧数据前扩展闭合枚举，并补带数据 V21→V22 升级回归。`9e93aca` 的 Java/Postgres 141 项全过、0 跳过（含真实升级测试），Python 224、web 126 和三个契约通过；Compose 在既有 15 项 PASS 后因新增脚本调用不存在的 v2 confirm 端点返回 404，后续并发/注册表未执行。脚本已改为现役开启复核→批准流程，精确断言旧日期批准返回 `DEPENDENCY_STALE`；完整新 head 验收仍待 CI。
- 本次审计还发现 `vue-tsc --noEmit` 在空根 references 配置下漏检页面；改为明确检查 `tsconfig.app.json`，修正文书刷新按钮把点击事件当 caseId 的实际缺陷并加点击验收。默认 env 演示改为完全 stub，文档说明注册/登录后 `/tasks` 入口与真实模型前置；修复六处已归档文档链接。
- 续查 A20/INV-LEGAL-003、006、007：旧模块将法源冲突/覆盖缺口写入 divergence 却仍 calculated，量刑遗漏双时点解析。现在按确认行为/裁判日期分别执行批准规则，保留两条未选定路径和实际规则/法源版本依赖；法源缺失、有效期重叠、覆盖缺口、语义不同及任一分支失败均阻断整体。候选/非法/冲突日期明确定位，缺失时保留显式基准日期路径与缺点信息。Java 拒绝携带冲突或 blockers 的确认并去重版本依赖；V23 前向迁移使旧 divergence 工件及显式依赖后代的确认/批准失效，保留不可变载荷和历史指针。
- 续查 A21/§14.1：requiredEvidenceKinds 原先只读未校验。现在仅对命中规则按既有 `entities.evidence[].type` 精确种类及 confirmed 状态检查，缺失/未核实/非法身份和容器阻断；没有引入别名映射或把类型匹配当司法证据充分性。前端显示双时点法源和规则版本、分支缺口及待核实种类；整体未择定时显示路径对照提示，失败分支隐藏数字。
- 本次新补丁经独立复审，修正了分支计算错误只存在结果级 blockers 而未提升整体状态，以及 Compose 脚本误取首条未命中规则的错误。最终本地 Python 非 integration 258 项、Ruff、三个 OpenAPI/快照、web 133 项及实际页面类型/生产构建通过；Java test-compile 通过。本机未运行真实 PostgreSQL；V22→V23 带数据迁移、版本依赖去重、真实双时点/证据缺失→candidate→confirmed 和既有全链路验证以此次新提交 CI 为准，尚未提前认定成功。
- `81c42d7` 的 CI `37698158027`：Python 258、web 133 和契约通过；Java/Postgres 145 项中两个新增依赖发布测试失败、0 跳过，Compose 未执行。真实 V22→V23 升级及冲突确认拒绝已通过。失败原因是共享 document.parse 夹具绕过模块发布，未测到新增法源依赖逻辑；现改为 compliance 回调并断言发布类型，不放宽依赖数量或拒绝断言。浏览器真实组件验收另发现异常载荷可同时展示缺证据和计算数字，已防御性检查嵌套规则阻断/缺失/未核实种类，并让状态标签与数字隐藏保持一致；窄屏提示改为纵向排列。本轮修正须通过新 head 完整 CI。
- `70d29b9c539d40a75b01b95ad00f7b9297a75c7d` 的 [CI 37698787047](https://github.com/alanzhang66666/lexcyber/actions/runs/37698787047) 五个 job 成功。完整日志：Java/PostgreSQL 145 项、0 失败/错误/跳过，含真实 V22→V23 升级、两个法源依赖回归；Python 258、web 134、真实页面类型/生产构建、三个 OpenAPI；Compose 18 项业务检查（新增双时点两分支/来源版本/批准拒绝，证据缺失→candidate→confirmed 与 CAS 绑定）、§19 三项真实并发、注册表数据库14项执行通过。桌面/390px窄屏真实组件检查覆盖有效未选定路径、非法嵌套证据状态下数字隐藏与提示排版；临时页面、依赖链接及本机服务已清理。
- 完整目标仍未完成：续查 A22，唯一权威 v1.3 §9.5 要求参数本身 confirmed 且有 evidence。当前证据种类检查不验证具体参数；在 main 与 70d29b9 实际运行仓库量刑语料，全部必需种类 confirmed、金额200000 confirmed，但 candidate 的 has_surrender=true 仍使12月基准变成8.4月，status calculated且无blockers（registry读取夹具，无真实数据库）。独立代理也复现该缺口。下一修复必须覆盖实际输入确认/证据关联、适用谓词/基准/调节与双时点，并核对文书取值和重复fact key，不能靠改阈值或“某种证据存在”放行。正式会签、B/C映射、真实供应商验证及合入仍未完成。
- 续查 A23/A24：证据重建 UUID 使 facts/amount/jurisdiction 引用悬空，参与人替换会清空 facts/events 关联。修复保持同案逻辑 actor/evidence 的 UUID，支持 snapshot 的 entityId/id/externalId 及 UUID 形状业务别名；引用中的实体删除明确 409，输入身份冲突提前拒绝。draft/确认/clone/已确认基线复用、模块/文书批准和归档都验证冻结证据与参与人引用闭包，不用当前工作副本替代旧快照。V24 根据坏快照沿正规化依赖递归失效旧确认/批准 head，保留全部历史与指针；有效历史实体即使当前已删仍可还原。
- 此补丁独立复审修正了共享门槛漏 actor、UUID 业务别名丢失及迁移漏非数组身份集合；Java test-compile、Python 非 integration 258 项、Ruff、三个 OpenAPI/快照通过。新增真实数据库损坏旧版本确认/clone/批准/归档拒绝、稳定身份/删除/别名回归、V23→V24 带数据升级，以及两项 HTTP/Compose 引用往返与跨案阻断检查。本机无 PostgreSQL，实际数据库与 Compose 行为须以新精确提交的 CI 为准，未提前认定完成；A22 仍未修。
- `4cc3d4e` 的 [CI 37702331958](https://github.com/alanzhang66666/lexcyber/actions/runs/37702331958)：Python258/web134/契约成功；Java/PostgreSQL162项、0失败、9错误、0跳过，Compose未执行。证据删除检查三个 EXISTS 的嵌套括号遗漏，各个证据写入回归均触发 SQL syntax error；现补闭合括号，未改引用政策、约束或测试断言。真实 V23→V24 带数据升级、坏旧快照归档阻断、有效冻结历史批准等测试已通过；整体仍须新精确提交 CI。
- `acf20de` 的 [CI 37702670252](https://github.com/alanzhang66666/lexcyber/actions/runs/37702670252)：Java、Python、web、契约成功。Compose 前17项业务检查通过，随后旧证据 fixture 用非 UUID 业务编号填 entityId，被新的身份校验返回400；新增引用检查、并发和注册表步骤尚未执行。fixture 改为用同一业务 id 将已有 candidate 证据更新为 confirmed，保留原缺失/未确认/已确认断言和严格 UUID 校验，须由后续精确提交重新验收。
- `e1e0775c94d3026041a38cc30225e09d3fff1dc7` 的 [CI 37703520801](https://github.com/alanzhang66666/lexcyber/actions/runs/37703520801) 五个 job 成功：Java/PostgreSQL162项、0失败/错误/跳过，Python258、web134及页面类型/构建、三个OpenAPI；Compose20项实际业务检查，包括稳定身份/引用往返、受引用删除原子拒绝、未知/跨案证据快照拒绝及有效历史clone恢复；§19三项并发和注册表真实数据库14项执行通过。V23→V24带数据升级和旧冻结引用/批准/归档防御已有实际数据库证据。A23/A24在该修复提交验收通过，仍draft/unmerged；main未变，A22独立缺口继续修复。
- A22 新增实际读取参数验证：保持 DSL lazy 真值/原规则阈值比例，普通谓词（包括 false）、基准档、调节项、日期、文书及两时点路径记录输入/证据身份、阶段和时点；候选、重复键、缺失/未核实/歧义证明均阻断。聚合沿原组成去重算法校验真实贡献行和非法数字；计数按实际行核验，空贡献不冒充已核实零。存在性缺失可作显式可选 guard，有值不能绕过核实。管辖至少一个 confirmed 且有有效证明连接，候选顺序不影响结果；actors/events 缺原生证明时不杜撰关联。顶层 marker 汇总全部已执行路径，阻断时量刑数字/步骤和文书正文均隐藏。
- v2 确认/批准校验严格 input_validation 版本、状态和数组形状，并检查同案递归上游；V25 前向失效缺少/损坏证明的有效 head 和正规化后代，保留全部载荷、确认/批准指针与已归档历史，legacy v1 保留。新增真实 V24→V25 带数据升级回归。仅 CI 合成规则的可选 selector 增加 exists 前置，成功 fixtures 显式关联 confirmed 参数证据；A21 service_log 种类缺失/candidate 用独立 document 参数证明隔离，不改真实 corpus 或生成正式批准。
- A22 本地 Python 非 integration295项、Ruff、Java21 test-compile、三个 OpenAPI/快照通过；真实 corpus 的9项回归确认 candidate 自首 true/false 均 blocked，全部已核实有证明时原8.4/12月结果保持，缺证据日期/重复日期和仅行为分支读到候选参数遮蔽全部数字。独立复审修正结构→强读取去重误放行、重复证据 canonical 首行裁决、嵌套缺值、非法金额数组、管辖顺序和跨案递归过滤；externalId-only 仅作别名不能冒充 canonical，id-only 兼容保留。实际 Postgres/Compose 新验收仍待精确新提交 CI，不以本地编译代替。
- `851bbf9` 的 [CI 37705034459](https://github.com/alanzhang66666/lexcyber/actions/runs/37705034459)：Python295/web134/契约成功，Java/PostgreSQL167项、3失败、1错误、0跳过，Compose未执行。V24→V25带数据升级已经执行，但载荷保真误比JSONB字段顺序；另有坏marker循环fixture重复scope、divergence fixture缺合法参数marker而遮蔽原MODULE_BLOCKED，以及归档递归证明校验遮蔽原ARCHIVE_ITEM_CROSS_CASE。现分别改JSON结构比较、独立fixture scope、证明与择法门闩隔离，并将完整归档同案校验置于证明校验之前；保持所有原业务/历史保真断言、唯一约束和严格证明门槛，实际回归须由新提交CI确认。
- 未扩张旧 prompt 数据库模型：追溯证明 PromptRegistry 只由未挂载到当前图的 worker 节点调用，当前 reserved 任务均直接进入 Engine adapter。该遗留副作用与现役路径不同，本轮未创建第二套 schema 或把旧库脚本当现役启动前置。

## 阶段状态

| 阶段 | 内容 | 状态 |
|---|---|---|
| 0 | 决策收口 + 基线冻结 | ✅ 完成：ADR-0001..0006、tag `arch-v13-baseline`、roadmap、文档指针 |
| 1 | 主键迁移到 uuid（V13 + legacy_id_map） | ✅ 已在开发库应用并实测（e2e 全链路 uuid 主键） |
| 2a/2b | 五张实体表 + FactsVersion/FactsHead | ✅ 已在开发库应用；全量快照 + CAS + diff/clone 实测通过 |
| 3 | ArtifactStream/ArtifactVersion + 依赖表 + execution_publication + 三套结果合并 | ✅ 发布幂等实测；模块/文书结果经 `publishModuleArtifact` 发布 |
| 4 | ModuleHead/DraftHead + 有效确认判定 + stale 传播 | ✅ 实测：facts 变更 → 工件 stale → 旧工件批准被 DEPENDENCY_STALE 拦截 |
| 5 | ReviewRecord 改绑 artifact_version_id + CaseArchive | ✅ 实测：复核裁决 → effectivelyConfirmed → `case.full.v1` 归档（manifestHash） |
| 6 | engine.execution 契约分离 + fencing + outcome envelope | ✅ engine V5 应用；waiting_review 展示态经 output_envelope 映射 |
| 7 | 统一幂等 + `/v2` 契约 + 前端迁移 + 删多 key 容错层 | ✅ 基本完成：V19 + IdempotencyService + `/v2`（18 paths）+ 前端逐页迁移 + `apiV2` 契约测试；payload schemaVersion 已在契约冻结（枚举），前端新增 `module-content-v2.ts` 严格读取器 + `RuleResultsPanel`（v2 工件此前在模块页显示为空——容错键不命中，现已修）；`module-content.ts` 容错层仅留 /v1 演示壳用途；文档/任务轮询/复核队列保留 /v1 兼容读层 |
| 8a | 法源/规则/模板注册与会签（P5 前置基建） | ✅ 代码完成并在真实库验证。engine/V6 注册表（legal_source + alias + supersession 链 + rule_package + template_package + signoff_record）+ `engine/rules/registry.py` + `/internal/v1/capabilities` 等 6 个内部端点 + `EngineCapabilitiesClient`；`/v2` 模块派发已接真实能力门闩（无 approved 规则 → `MODULE_EXECUTION_UNAVAILABLE`，有能力但适配器未实现 → `ENGINE_ADAPTER_PENDING`） |
| 8b | 规则层（合规/定罪/界分执行体） | ✅ 第一片已验证：evaluator DSL + `module_analysis.py` → case.*.v2 payload + 逐条件 trace + fired 规则双时点法源解析；e2e 实测 calculated/not_applicable/blocked 三态。剩余：规则语料扩充（当前 7 条底稿） |
| 8c | 可解释量刑（注册表化） | ✅ 第一片已验证：base_tiers 择档 + when-gated adjustments + 显式夹逼留痕 + ROUND_HALF_UP，产出 sentencing.v2；旧 metadata 重放保留兼容。剩余：地方细则插件、缓刑/罚金独立计算块 |
| 8d | 文书渲染 | ✅ 渲染链已验证：`draft.render` → draft.v2 + 占位符阻断 + 上游 payload 代入；模板按案型分（`indictment-assist` 通用 + `indictment-draft` 支付结算型）。DOCX 下载代码与验收已补齐，精确新提交的 CI 结果以 PR 检查为准。当前输出是辅助正文排版，不宣称使用法学 DOCX 版式模板，也不包含 PDF 导出。 |
| 9 | 法源层 + AI 边界 + 门闩双侧 + 可观测性 | 🔶 法源注册 + 双时点解析（`resolve_temporal`）已随 8a 落地；新旧链数据、AI 边界审计、可观测性未做 |

## 验证状态（2026-09-24 实测）

**环境已就位**：Docker 29.7.2、`maven:3.9-eclipse-temurin-21`（容器化编译，宿主无 JDK/Maven）、Python 3.13.2、Node 25。

**关键事实**：现有 `postgres_v03` 卷只应用到 app V11 / engine V4（6 案 15 档 24 复核 28 任务）。**V12–V19 与 engine V5 是未发布迁移**——无 checksum 漂移，可按需修改；「已执行迁移前向修复」预案未启用。全量备份：`~/lexcyber-backups/lexcyber-pre-v13-20260924.dump`。

**已验证**：

| 项 | 结果 |
|---|---|
| `mvn compile` + `test-compile` | ✅ 通过（修了 FactService 缺 `Map` import、EngineDispatcherTest 构造器） |
| Flyway V1–V19 存量升级（真实数据副本） | ✅ 通过；首次跑暴露并已修 6 个迁移级缺陷（见下） |
| Flyway V1–V19 全新安装（`lexcyber_test`，lex_app 身份） | ✅ 通过 |
| engine V1–V5 | ✅ 通过 |
| `python -m pytest -q` | ✅ 105 通过 / 1 跳过（修了 4 个 `complete_execution` 新签名 stub 与 `timed_out`→`failed` 断言） |
| `ruff check engine/`、`py_compile` | ✅ 通过 |
| `npm --prefix web run build` | ✅ 通过（早前一轮） |
| Java 单测（TEST_JDBC_URL 外部库路径） | ✅ 84/84 通过（75 旧 + 9 新 FactsBaselineServiceTest） |

**首验发现并修复的缺陷**（全部发生在未发布迁移/未验证代码上，未造成真实损失）：

1. V14：`case_amount` 建表缺 `attributes` 列（INSERT 引用）；`verification_status` varchar(32) 放不下演示数据的 44 字符状态 → 加列 + 放宽 64。
2. V15：DO 块内 `rv` 别名与 DECLARE 变量冲突（两处）；**更严重**：非 parse 任务（13 条 `sentencing.calculate` 执行结果）完全不回填——结果与复核全丢。已改为「模块流 = 执行版本 + 手工正文版本」合并回填，未映射任务类型写审计。
3. V16：回填引用不存在的 `s.module` → `ms.module`。
4. V17：**原逻辑会静默删除 12 条真实复核**（actor 解析失败 + `case_id` NULL → `DELETE WHERE actor_id IS NULL` 无审计）。已修：case_id 由绑定 artifact 回填、actor 解析链扩为 username→artifact 案 owner→task 案 owner、代位写 `review_actor_substituted` 审计、仍失败的审计后删。实测 24/24 保留。
5. V13：`pgcrypto` 未指定 schema，随 Flyway 迁移期 search_path 装进 `app` schema，业务角色运行时找不到 `digest()` → `WITH SCHEMA public` + `ALTER EXTENSION ... SET SCHEMA public`。
6. Java：`queryForList` 对 timestamptz 返回 `Timestamp` 强转 `OffsetDateTime` 崩（FactService 加 `toOffset`）；`stream.findFirst()` 对 NULL 列 NPE（3 处 `flatMap(ofNullable)` → `filter(nonNull)`）；幂等冲突码改回契约冻结的 `IDEMPOTENCY_CONFLICT`；`module_head.stale DEFAULT true` 被 `factsStale` 误读（从未确认≠事实已变，改按 `stale_reason` 非空计）。

**本轮（P1–P4 续）已落地并测试通过的修改**：

1. **FactsVersion 全量快照**：`createDraftVersion` 覆盖六类实体（items + entities 分节），`facts_version_item` 登记全部成员（条目级语义哈希）。
2. **confirm CAS**：`expectedConfirmedFactsVersionId` 入参，锁内比对不一致 → `409 FACTS_HEAD_CONFLICT`（§4.8.1 后到者不得静默覆盖）。
3. **事实闭环端点**：`GET facts-versions`（历史）/ `GET …/{id}`（含 payload）/ `GET …/diff?against=`（added/removed/changed 分节）/ `POST …/clone`（快照回写工作副本，不碰 head 与旧版本）/ `GET|PUT facts-entities[/kind]`（/v2 工作副本读写；确认后仍可编辑，仅影响下一次快照）。契约与 api-types 已同步（INV-CONTRACT-001）。
4. **发布幂等加固**：`execution_publication` 检查抽到 `publishedVersionOrThrow`，stream 行锁内重查——并发双发不再撞唯一索引变 500。
5. **统一锁序审计修复**（原实现存在真实死锁环）：`publish` 按 stream→head→review 加锁，而 confirm/approve/decide 按 head/review→stream 加锁，可互相等待。已将 `ModuleConfirmationService.confirm`、`DraftApprovalService.approve` 改为 stream SHARE → head UPDATE；`ReviewService.decide` 在 review UPDATE 前先取 stream SHARE。全局序：`case → facts_head → stream → head → review → publication`。
6. **派发期绑定**：`TaskService.create/retry` 按 taskType 解析 (kind, scope_key) → `ensureStreamLocked` → `ExecutionRequest.artifactStreamId`；输入快照引用：`document:{id}@sha256:{hash}`（DocumentService metadata 已带 sha256）或 `facts_version:{id}`。有案模块任务缺 confirmed FactsVersion → 409。
7. **V2 契约修复**：`name: x; in: path` 分号写法是非法 YAML，9 处全展开；pyyaml 解析通过（16 paths/14 schemas/8 params）。`FactsBaselineServiceTest` 新增 8 用例覆盖上述验收点。

**本轮（P5/8a 注册表）已落地并实测通过**：

1. **engine/V6 注册表**：`legal_source`（source_key+source_version 唯一、生效区间、authority 封闭集、coverage 边界、content_hash）+ `legal_source_alias` + `legal_source_supersession`（显式新旧链，INV-LEGAL-005）+ `rule_package`（family 封闭集、source_ids 绑定具体版本、required_evidence_kinds）+ `template_package` + `signoff_record`；`lex_engine` 受限角色授权实测通过。
2. **三层触发器防护**：approved/superseded 禁删；approved 内容冻结仅允许 approved→superseded 退役；`approved`/`rejected`/`signed_off`/`disputed`/`unsupported` 评审结论必须走 `signoff()` 同事务路径（`engine.signoff_authorized` GUC，直连 SQL 被拒——实测验证）。
3. **`engine/rules/registry.py`**：`register_*` / `signoff` / `capabilities`（模块可用性 = 所需 family 全有 approved 包）/ `active_rules`（approved-only 产出面，INV-RULE-002）/ `resolve_temporal`（双时点解析：跨版本 → `LAW_VERSION_DIVERGENCE` 阻断自动择一；区间外 → 覆盖缺口不近似，INV-LEGAL-006/007）/ `coverage_check`；`seed.py` 语料播种（10/10 已入册，文种映射保真）。
4. **内部端点**：`/internal/v1/capabilities` + `/internal/v1/registry/{legal-sources,rules,templates,signoffs,resolve}`，全部 `X-Service-Token` 门控；`internal-engine-api.yaml` 已同步。
5. **Java 门闩接通**：`EngineCapabilitiesClient` + `V2LifecycleService.dispatchModuleExecution` 改为真实能力查询。
6. **验证**：`tests/integration/test_rule_registry.py` 8/8 通过（真实 V6 schema：登记/重复拒绝/无 GUC 批准被拒/approved 不可变/会签退役/未知 source 绑定拒绝/双时点 divergence+缺口/模板会签/能力映射）；engine-migrate V5+V6 干净应用 + repair 校验和同步。

**本轮（P10a 全栈端到端）已实测通过**：

1. **五段管道全链路跑通**（compose 全栈，HTTP 驱动）：注册 → 建案 → facts/amounts 实体写入 → FactsVersion 建版 + CAS 确认（v1→v2）→ 定罪/合规/量刑派发 → Engine 消费 approved 规则包执行 → 工件发布（`case.conviction.v2`/`case.compliance.v2`/`sentencing.v2`/`draft.v2`）→ 复核裁决 → `effectivelyConfirmed=true` → `case.full.v1` 归档（manifestHash + 3 工件入册）。
2. **失效传播实测**：facts v2 确认后旧工件 stale；对基于 v1 的合规工件批准被 `DEPENDENCY_STALE` 正确拦截，重跑 v2 后批准通过。
3. **渲染阻断实测**：模板含未解析占位符（`defendant_name` 缺失 / `amounts.inflow.confirmedSum` 非法 kind）→ `blocked` 且不产正文；修正模板 1.0.1 + 补事实后 rendered。
4. **修复三个真实缺陷**：
   - `input_hash` 409 循环——factsSnapshot 里 BigDecimal 保 scale 序列化（`8000.0000`）与 Python `json.dumps`（`8000.0`）canonical 不一致；`TaskService.normalizeJson` 派发前归一化，`TaskServiceHashTest` 覆盖。
   - 模块/文书结果不发布——`EngineResultService` 只认 document 解析任务；新增 `publishModuleArtifact`（kind/scope_key 与派发绑定一致，schema_version/status/依赖快照取自 payload，rules/template/sources → external_dependency，draft 上游模块 → artifact_dependency）。
   - nginx 无 `/v2/` 路由（405）——已补 `nginx.v03.conf`。
5. **注册表清理**：corpus 规则 `settlement`/`inflow` → `payment_settlement_amount`（ADR-0003），两条规则升 1.0.1 并会签，旧版退役；残留 approved 测试规则/模板（`it-*`、旧 `fact:` 谓词、`indictment-draft@1.0.0`）全部退役。
6. **开发库补齐**：app schema V12→V19 由 `lex_migrator` 应用（Java Flyway 用 `lex_app` 无 `pgcrypto` 权限）；V14+ 表补 `lex_app` 授权。

**本轮（P10b 受控演示）进展**：

1. **三案导入完成**：`scripts/import_three_case_demo.py`（demo_runner 账号）——A/B/C 建案 + 文档上传解析 + facts + 模块壳全部 completed=3/failed=0。
2. **语料代差发现**：demo bundle 事实是叙述文本（`type` 作键），金额 kind（`non_crime_flow`/`personal_profit`）在 ADR-0003 封闭集外——不能直接进规则管道。为案例 A 编写了**键化覆盖层**（knowledge_of_crime/help_type/contact_timing 等按 bundle 已审定结论映射，locator 注明 `bundle:*` 出处；28万→`business_revenue`、3万→`illegal_gain`、96万→`crime_amount`，不写 `payment_settlement_amount`——忠实于「非支付结算」的原审定）。
3. **案例 A 全管道实测**：定罪 calculated（构成要件+`illegal_gain≥1万`严重度命中；掩隐界分、诈骗共犯正确不命中）；量刑 9.0→8.1 月（base tier+坦白）；文书渲染因模板需 `payment_settlement_amount` 正确 `blocked`——案例 A 本就不是支付结算型，fail-closed 行为正确。
4. **CAS 并发实测**：错误 expected head → `409 FACTS_HEAD_CONFLICT`。
5. **发现的口径分歧**：bundle 审定基准 12–18 月 vs corpus 量刑规则算出 8.1 月——规则基准档与案载裁量有偏差，属规则语料精度问题，留待法学评审校正。

**本轮（收口整理）已落地**：

1. **V20 授权迁移**：`lex_app` 对 app schema 全部表/序列的 CRUD 授权 + migrator 新建对象默认授权，固化此前手工执行的 GRANT；角色缺失/权限不足时降级 WARNING 不炸迁移。
2. **`app-migrate` compose 服务**：app schema 迁移由 `lex_migrator`（POSTGRES_USER）执行，Java 启动 Flyway 仅校验——修复全新环境 `lex_app` 无 `pgcrypto` 权限导致的 V13 失败。engine/engine-worker 共用 `image: lexcyber-v03-engine:latest` 消除镜像漂移。
3. **`/v1` 模块写层退役**：PUT 模块壳 + POST confirm 默认 `410 MODULE_WRITE_RETIRED`，仅 `DEMO_IMPORT_ENABLED` 放行；契约标 deprecated；导入脚本容忍 410 记 `skipped_write_retired`。
4. **v2 payload schema 冻结**：`ArtifactVersionView.schemaVersion` 改枚举（document.parse.v1 / case.module.v1 / case.compliance.v2 / case.conviction.v2 / sentencing.v2 / draft.v2）；前端新增 `module-content-v2.ts` 严格读取器 + `RuleResultsPanel` 组件——此前 v2 工件在模块页全部显示为空（容错键不命中），现定罪/合规页展示规则逐条 fired + 逐条件 trace；AnalysisPage 金额改读确认事实快照（原读定罪 payload，v2 下本为空）；DocumentsPage 渲染结果走严格读取。
5. **模板按案型**：`engine/rules/corpus/core_templates.json` 新增 `indictment-assist` 通用模板（无 payment_settlement_amount 占位符）；`seed --templates` 播种路径。
6. **§19 并发脚本**：`scripts/concurrency_check.py`——双确认 CAS（409）、双发布重放（工件版本稳定）、归档/复核交错（无 5xx）；internal 用例需容器网内执行。
7. **文档归档**：11 篇历史文档 + 根 `PLAN.md` → `docs/archive/`（git mv 保历史 + 归档横幅）；`AGENTS.md`/`README.md` 按现状重写；`docs/legal-signoff-checklist.md` 补法学待签清单。

**仍待办**：案例 B/C 键化覆盖层（需法学审定映射）、真实法学负责人会签（当前 e2e 占位，含新增 `indictment-assist` 模板）、量刑基准档与案载裁量偏差校正（法学）。文书 DOCX 下载与验收已补齐；§19 脚本已随 2026-10-08 修复纳入每次 CI 的 Compose 网络，已执行证据见上节。

## 2026-10-08 定罪路径完成度续查

- A22 修正提交 `90024da128fc04291b2c4e92caca971478914eae` 的 [CI 37705884129](https://github.com/alanzhang66666/lexcyber/actions/runs/37705884129) 五个 job 全部成功：Java/PostgreSQL167项、0失败/错误/跳过（真实V24→V25升级及历史载荷保真），Python295、web134、三个OpenAPI；Compose21项业务检查，含实际参数candidate真假/缺失或候选proof阻断→有效linked proof批准，§19三项并发及注册表数据库14项通过。
- A25：兼容T1投影和页面原本丢弃已有 `exclusion_reason`；补丁原样保留蛇形/驼峰字段并独立展示，保留概述、排除状态、双方证据和原始输入。没有推定排除理由或修改冻结/演示法学底稿；无理由时保持缺失，不伪造文本。新增两项真实构建器回归与既有页面读取/组件展示断言。新补丁验收独立于以上90024da结果。
- 本次补充明确声明的 `outcome.candidate_paths` 通用执行能力，见 [定罪路径契约](conviction-path-plan.md)：按冻结参与人绑定路径，保留规范证据身份、双方证据、排除理由、规则/法源版本及独立时点；主观路径有相反证明输出 conflicted，整体 blocked 时清空可裁断位置。页面严格读取且保留诊断，不把未复核路径显示为确认排除。false 分支必须由计划明确声明，不从旧字段推定法律含义；仅标签变更不构成择法业务分歧。
- A26/P1：V6 只保护 UPDATE/DELETE，注册 API 与直接 INSERT 可写入 approved/signed_off，绕过正常 signoff。新增 V7 首次插入守卫及有批准记录的有效视图；执行读取还要求引用法源已签署，旧绕过行留在历史但不进入有效集合。原 V6 与历史载荷不修改。真实 V6→V7 升级、降级和数据库守卫等待本次精确提交 CI。
- 本地 Python 非 integration323、web142、真实 Vue 页面类型/生产构建、三个 OpenAPI/快照及 Ruff 通过。新增 HTTP 用例待 CI 验证：2200/2201 隔离合成计划、已核实路径批准、未核实证明与主观冲突拒绝批准、历史不变。CI 规则与签署均仅是技术夹具。
- INV-CONV-001/002/004 仍未完整交付正式语料映射，INV-CONV-005 请求罪名覆盖接口尚缺；没有路径计划的旧规则保持诊断与空候选路径。真实法学会签、B/C键化映射及量刑基准校正仍待负责人资料，不通过改默认501或生成测试签署冒充完成。

## 关键不变量速查

- 计算单元三态：`calculated | blocked | not_applicable`，`blocked` 不是 `failed`
- 发布绑定：`execution_publication` 权威 + `artifact_version.execution_id` 部分唯一索引（ADR-0001）
- `FactsVersion` 不存 `status` 列，DTO 派生（ADR-0002）
- 金额 `kind` 封闭 6 类 + `component_of`（ADR-0003）
- 「从未确认」= `confirmed_version_id IS NULL`（ADR-0004）
- 有效确认 = `confirmed_version_id != null && !stale`；批准时依赖校验是第二道防线（ADR-0005）
- `archive_version` 由 `cases.next_archive_version` 分配（ADR-0006）

## 待补（v1.3 已标 TBD，不属本 roadmap 主线）

- 认证授权模型、RBAC/ABAC
- `case.full.v1` 归档必需项细化
- 错误码完整目录
- 审计事件统一 schema、checkpoint 粒度、execution 重试策略
- 部署拓扑 / HA / DR / RPO / RTO / NFR
