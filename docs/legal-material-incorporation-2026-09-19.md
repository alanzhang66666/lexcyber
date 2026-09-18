# 法学材料盘点与补充报告（2026-09-19）

来源目录：`法学材料/`（18 个文件）。本报告区分三类：已入库的工程数据 / 候选法源与字段（待法学会签）/ 仅归档的过程材料。

## 1. 已入库：三案真实材料（sha256 验证通过）

演示库已重置重建（`down -v` + 重灌），以下文件与 `demo_cases/three_case_demo/*.json` 中 bundle 声明的 `archive_entry` + `sha256` **逐字节一致**：

| 案件 | 文件 | 角色 | 状态 |
| --- | --- | --- | --- |
| A | 演示案例A/合成案例011（改）-输入材料.docx | case_material → input | ✅ 已上传+解析（真实案情全文） |
| A | 演示案例A/合成案例011（改）-法学标注.docx | benchmark_annotation → annotation | ✅ 已上传+解析 |
| B | 演示案例B/合成案例009（改）-输入材料.docx | case_material → input | ✅ 已上传+解析 |
| B | 演示案例B/合成案例009（改）-法学标注.docx | benchmark_annotation → annotation | ✅ 已上传+解析 |
| C | 演示案例C/合成案例016-输入材料.docx | case_material → input | ✅ 已上传+解析 |
| C | 演示案例C/合成案例016-法学标注.docx | benchmark_annotation → annotation | ✅ 已上传+解析 |

当前文档清单：A/C 各 1 输入 + 1 标注；B 为 2 输入 + 1 标注（042 件仍为占位，见下）。

## 2. 未能入库（需人工处理）

| 文件 | 原因 |
| --- | --- |
| `042输入材料新.doc` / `042法学标注新.doc` | `.doc` 旧格式——bundle 期望的是 `.docx` 转换版（`042输入材料新(1).docx`），库内不存在该文件；API 仅收 PDF/DOCX。**B 案的 042 输入材料当前仍是占位上传**。需法学/业务侧提供 docx 版或人工转换后再以新修订 bundle 导入 |
| `演示案例说明.docx` / `(1)` / `(4)` | 三份均为「验收基准确认清单」的**不同修订版**，与 bundle 声明的 sha256 均不符（bundle 期望 `说明(1)`=`6ec30f14…`、`说明(4)(1)`=`b1b3c027…`）。其中 `(1)` 版已部分标注"适用"，`新建+DOCX+文档.docx` 为已填事实确认清单——**这是 L2/L3 法学验收签字件本体**，按你的指示仅归档于 `法学材料/`，未入系统 |
| `新建+DOCX+文档.docx` | 同上，验收清单已填版 |

## 3. 法律文书模板：3/3 哈希匹配，无需改动

`法律文书模板.zip` 内三个文件与 `document-templates.json` 登记的 `source_archive`+`sha256` 完全一致：

- `不起诉决定书.docx` → `cn-non-prosecution-template-v1`
- `起诉书.docx` → `cn-prosecution-template-v1`
- `量刑建议书.docx` → `cn-sentencing-recommendation-template-v1`

登记表 `legal_review_status = source_templates_provided_mapping_pending_approval` 依然准确——源文件已验证在位，**字段字典/映射仍待法学会签**，工程侧不做改动。

## 4. 新增法源候选清单（待法学会签，未入 adapter）

`法律法规及司法解释.zip` 共 16 个全文文件。与 `engine/adapters/legal_sources.json`（10 条摘录级记录）比对：

**已被 registry 覆盖**（无需动作）：刑法全文（对应 287之二/266/312/6-7 四条摘录）、帮信意见、电诈意见（一）、非法利用信息网络/帮信解释（法释〔2019〕15号）、量刑指导意见（二）。

**候选新增**（全文文件在包内，需补 source_id/生效日/条文定位/摘要后由法学确认）：

| 候选 source_id | 文件 | 关联 |
| --- | --- | --- |
| `cn-criminal-procedure-law-2018` | 中华人民共和国刑事诉讼法(2018修正) | 程序底座 |
| `cn-procuratorate-criminal-procedure-rules-2019` | 人民检察院刑事诉讼规则(2019) | 程序底座 |
| `cn-enterprise-compliance-measures-trial` | 涉案企业合规建设、评估和审查办法(试行) | **模块一合规筛查直接相关** |
| `cn-third-party-compliance-eval-guidance-trial` | 第三方监督评估机制指导意见(试行) | **模块一直接相关** |
| `cn-criminal-procedure-interpretation` | 最高法刑诉法解释 | 程序 |
| `cn-crossborder-telefraud-opinion` | 跨境电信网络诈骗意见 | **C 案跨境场景直接相关** |
| `cn-computer-security-interpretation` | 危害计算机信息系统安全解释 | 网络犯罪类 |
| `cn-telefraud-opinion-2` | 电诈意见（二） | 补 registry 仅有 2016 版 |
| `cn-extraterritorial-law` | 域外法律.docx | 定罪页管辖/域外段 |
| `un-cybercrime-convention` | 联合国打击网络犯罪公约 | 域外/条约 |

**缺口提示**：registry 中两条掩隐解释（`cn-concealment-interpretation-2015-2021`、`cn-concealment-interpretation-2025-1-12`）在本包中**无对应全文**——若法源包是权威全集，这两条摘录的来源文件需法学另行提供。

## 5. 关键发现：专家标注工作簿可补定罪页缺口

`法律专家标注工作簿_v1.xlsx`（90 案逐案标注，11 列）与现有模块字段高度对应：

| 工作簿列 | 现有对应 | 状态 |
| --- | --- | --- |
| 案例编号/名称 | datasetCaseId / title | 已对应 |
| 罪名定性 | conviction candidate_paths | 已覆盖 |
| 犯罪行为及证据 | facts + evidence + events | 已覆盖 |
| 时间关系 | events 时序 | 已覆盖 |
| 合规情况 | compliance 模块 | 已覆盖 |
| **主观线索及结论** | **conviction 04 段（当前写死"待引擎输出"）** | **候选补充** |
| 否定性事实 | conviction excluded/blocked 路径 | 部分对应 |
| 管辖线索及结论 | conviction 05 段 jurisdictionConnections | 部分对应（已接线） |
| 犯罪数值及依据 | amounts | 已覆盖 |
| 裁判结果及裁判理由 | sentencing benchmark_disposition | 已覆盖 |

三案实际标注内容示例（原文存 `.tmp-wb-demo-cases.json`，已校验）：

- **009 主观线索**：黄某明知上线利用网络实施诈骗+明知资金犯罪关联+主动提供账户取现+获利4200元；结论"员工明知不能直接等同于企业明知"
- **011 主观线索**：冯某知 GOIP 被诈团伙利用风险+发现隐藏号码/批量拨号异常+仍持续销售+个人获利；结论"冯某主观认识不能当然归属于甲公司"
- **016 主观线索**：客户身份异常+无法提供资质+要求境外服务器/隐藏主体/规避监管+管理层获具体风险信息后仍继续；结论"不是单纯应当知道，而是获风险信息后仍决定继续"

**处置建议**：工作簿"主观线索及结论"列是定罪页 04 段的**候选数据源**——工程上可将其结构化为 `subjectiveKnowledge`/`subjectiveConclusion` 字段投影进 conviction 模块 content，但这属于新增 T3 字段，**需法学确认字段名与口径**后方可写入 bundle，不擅自映射为结论。

## 6. 批量语料（未来扩展，本轮不动）

- `合成案例40个.zip`（121 项）/ `合成案例（3）.zip`（151 项）：含 009/011/016 的**未修订原版**（与演示用"（改）"版哈希不同），另有 40+ 案输入+标注对
- `051-060.zip`（31 项）：010–060 号段案例
- 两份 `(1)` 后缀 ZIP 与对应无后缀版**内容相同**（重复副本）

用途：未来批量导入/benchmark 语料。当前演示的三案必须用"（改）"修订版，不动。

## 7. 本次运行时变更记录

1. `docker compose down -v` 全量重置演示库（已确认）
2. 修复 `infra/postgres/init/001-roles.sh` CRLF 行尾 → LF（fresh 卷 initdb 才能执行）
3. `import_three_case_demo.py --docs-dir .tmp-legal-docs --allow-placeholder --register-account` 重灌三案（042 输入件回退占位）
4. 上传 3 个真实法学标注（annotation 角色）
5. 确认 facts → 模块重绑 v2（stale=False）→ 归档 3 个死 v1 复核 → 开 3 个 v2 定罪复核
6. `docker cp` 更新 engine+worker 容器代码（镜像未含 t3-round3 的 replay 分支）+ `docker cp demo_cases`（镜像未含演示数据目录）→ 重建 2 个量刑任务：C案甲某 8–14月/8000–15000、A案冯某 12–18月/5000–10000，均 `reviewed_disposition_replay` + 留痕
7. 归档 2 个旧 blocked 运行产生的量刑复核

当前 pending 复核队列：3 定罪（v2）+ 2 量刑 = 5 条，与重置前演示态一致。

## 8. 遗留环境注意

- Engine/Web/Java 镜像均为"离线拼装"（docker cp 代码 + 本地 dist/jar），**`docker compose up --build` 在有网环境才可全新构建**；`engine/Dockerfile` 的 `COPY demo_cases` 修复已入库但镜像未重建
- `.tmp-legal-docs/` 为解压出的真实材料工作目录（gitignore 覆盖），供重灌使用
