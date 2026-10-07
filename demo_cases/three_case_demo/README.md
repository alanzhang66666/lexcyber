# 三案演示基准包（T3）

本目录是 `LAW-01` 的机器可读交付，不替代司法裁量。A、B、C 分别覆盖帮助行为、资金处置界分、单位/合规/涉外连接点。2026-09-18 根据法学团队补充结论和用户本地材料，将基准包更新为案例 011（改）、009（改）+042（改编终稿）、016；每个文件都记录了相对材料路径和 SHA-256，以便回查。

## 当前状态

- 三个 JSON 包均通过结构、唯一 ID、引用和金额格式校验。
- `baseline-scenarios.json` 冻结 A/B/C 的实体数量、逐案法源时点、正常路径、缺证/冲突路径，以及交给 T1 的 `datasetCaseId`、`t3BundleId`、`factsVersion`、`sourceVersion` 追踪字段。
- “输入材料”记作 `case_material`；“法学标注”和“演示案例说明”只记录核验结论，不作为案件证据。
- 法学终版清单逐项确认的事实已标记为 `confirmed`，待补信息保持 `candidate`，存在相反证据的字段保持 `conflicted`。
- A、C 的候选罪名与排除路径已按终版清单更新；B 已补入案例 042 输入材料和法学标注，并与案例 009 组成帮信/掩隐对照。
- 042 原文件是 T1 不支持上传的旧版 `.doc`，本地生成了全文一致的 `.docx` 副本；bundle 同时保存原文件哈希、转换后哈希和全文比对哈希。
- 042 原案二审维持帮信罪；补充材料是将定性和刑期改成掩隐罪的教学改编。两条路径和两组结果必须分开显示，改编刑期不得冒充真实裁判或系统计算结果。
- A 案金额口径已确认：28 万元是公司经营性设备销售收入，不是支付结算金额或犯罪所得；冯某个人 3 万元是违法所得；96 万元是上游诈骗犯罪金额及被害人损失。
- B 案 009 法学标注区间已确认为拘役 4 个月至有期徒刑 8 个月、罚金 3000-10000 元。适配器按“已审阅宣告刑建议”重放该区间，不把它表述为模型自动推算结果。
- C 案金额口径已确认：11.8 万元作为单位帮信违法所得评价，9.8 万元是其组成部分且不得重复相加，2 万元是技术人员个人违法所得；上述金额均不作为支付结算金额。现有境内行为地和结果地足以确认中国刑事管辖权，七项未查明境外信息不再作为管辖阻断项。
- 法学团队已提供起诉书、量刑建议书和不起诉决定书三个 DOCX 源模板；`document-templates.json` 记录文件哈希、结构、字段和条件分支。三份模板使用正文 `【…】` 占位符，不含 Word 表单字段或内容控件。
- 模板“已提供”不等于字段映射“已会签”。生成草稿只能使用已确认数据；任何未替换占位符、未选择条件分支或缺少必填字段都会阻断批准并进入人工复核。
- 文档第六部分的最终宣告刑建议已逐主体登记为 `reviewed_disposition`。适配器直接重放已审阅的区间、确定刑期、罚金和追缴数额；起点、调节比例和法源仅作为审计说明保留，不再为无法唯一复算宣告刑而返回 `blocked`。
- 公开检索、量刑及分析开关继续保持关闭，不能因为数据包更新而自动启用。
- 案例包中的 `approved` 仅表示既有法学摘要允许内部基准回放，不等于部署级法源会签；当前法源目录和基准清单统一保持 `signoff_status=pending`、`public_eligible=false`，不得据此输出公开法律结论。

## 使用

```python
from engine.adapters import (
    calculate_case_sentencing,
    load_case_bundle,
    search_legal_sources,
    validate_case_dataset,
)

report = validate_case_dataset()
case_b = load_case_bundle("B")
sources = search_legal_sources("2025掩隐解释", as_of_date="2026-09-18")
sentencing_result = calculate_case_sentencing(case_b, "actor-b-huang")
```

也可直接运行 `python scripts/validate_three_case_demo.py` 输出完整校验报告；导入契约由
`contracts/schemas/collaboration-case-index.schema.json` 和
`contracts/schemas/collaboration-case-bundle.schema.json` 冻结，T3 本轮基准契约由
`contracts/schemas/three-case-baseline.schema.json` 冻结。验证顺序是 JSON Schema、跨文件身份与引用、实体/证据完整性、法源生效区间与会签门闩、正常/阻断场景及 T1 追踪字段；任一步失败时退出码为 1，法学待核项保留为 warnings。

场景校验要求正常路径没有修改或阻断，状态为 `waiting_review/calculated`；负向路径必须包含与路径类型、主体匹配的证据移除或冲突事实，状态为 `blocked/blocked`，阻断码与事实 ID 必须逐项对应有效修改。该检查验证基准声明的一致性，不表示执行了定罪或量刑分析器。

对 `applicable_to_conduct=true` 的法源，校验器以 bundle 中结构化的 `conduct_period` 和法源目录生效区间为准，要求覆盖整个行为期间（含首尾日期）。行为结束时间未知时，不能声明有截止日期的法源覆盖全程。`application_time` 仅为说明文字，不作为时点校验依据；后续法源可以保留为非行为时适用的复核参考。该检查不代替法学负责人对具体适用问题的会签。

索引必须提供稳定的 `producer_id`、`dataset_id`、`revision` 和每案 `external_case_id`。其中
`producer_id + external_case_id` 是协作身份，`dataset_id + revision` 是本次交付版本；不得使用标题、文件名或数组位置推导身份。

联调上传真实材料前，先设置固定账号（不得依赖随机注册）：

```powershell
$env:LEXCYBER_USERNAME = "<local import account>"
$env:LEXCYBER_PASSWORD = "<local password>"
python scripts/import_three_case_demo.py --docs-dir "F:\1项目\111量刑预测"
```

首次有意创建该固定账号时额外传 `--register-account`。凭据只放环境变量，不写 checkpoint 或仓库。

导入器在任何网络写入前校验全部数据包、材料存在性和实际 SHA-256。它把恢复状态原子写入
`.t1-three-case-import.checkpoint.json`，记录外部案件/材料到 Java ID 的映射，但不保存 token 或密码；重复运行会核对服务器现状并从最后完成步骤继续。同一 checkpoint 绑定 base URL、用户名、producer、dataset、revision 和数据摘要，任一变化都会拒绝复用。可用 `--checkpoint <path>` 为不同目标分离状态。

已有旧版三案数据只有 `datasetCaseId + t3BundleId`，没有新的协作身份。默认导入会停止而不是重复建案；确认目标无歧义后，可一次性用 `--adopt-legacy` 将唯一旧案件写入本地 checkpoint。案件创建、材料上传和复核开单都使用稳定 `Idempotency-Key`，Java 通过 Flyway V10 持久绑定请求内容与返回资源；同一身份在请求响应丢失或多客户端并发时会重放同一资源，不会重复创建。

缺材料时导入失败并列出缺失的 `case_material`，不会默默上传 `.t1-smoke-input.docx`。本地冒烟才加 `--allow-placeholder`；占位文件会在报告中明确标识，不能作为实际交付。

导入器只上传 `case_material`，不会把法学标注或终版说明当作案件证据。由于公开上传接口只接受 PDF/DOCX，运行前应确认根目录存在 `042输入材料新(1).docx`；原 `.doc` 仅用于来源追溯。

T1 可直接把 bundle 作为内部输入映射到案件、任务和结果版本；T2 可按 `actors`、`events`、`evidence`、`facts`、`amounts`、`analyses` 和 `document_fields` 渲染。不得把 `benchmark_position`、`benchmark_disposition` 或 `baseline_asserted` 显示为已审核结论。

## 后续收尾顺序

1. 042“办理贷款”辩解继续作为相反材料展示；27 个月改编结果只能标记为教学演示中的已审阅建议，不能冒充原案裁判或算法推算结果。
2. 对已登记的三份源模板完成字段映射、条件分支和缺项处理；完成前不得把模板状态标为 `approved`。
3. 完成收集方式、清洗方法、许可证/授权、实质改造和脱敏措施的案例来源台账。
4. T1 完成任务链联调后再开启公开量刑入口；当前 Engine 结果仍要求人工复核。
