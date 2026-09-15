# T3 三案数据、法源与计算交接说明

版本：2026-09-14（待法学负责人会签）

## 交付范围

本次实现提供 T3 内部能力，不新增公开 API，也不替 T1 保存任务/结果或替 T2决定页面法律文案：

- `demo_cases/three_case_demo/`：A/B/C 三案机器可读样例、原文件路径和哈希、事实—证据—阶段—金额—候选路径映射。
- `engine/adapters/case_bundle.py`：加载单案、检查重复编号/缺文件/引用完整性/审批状态。
- `engine/adapters/sources.py`：仅检索三案涉及的九条版本化官方法源记录；超出范围明确返回 `unsupported_query`。
- `engine/adapters/sentencing.py`：仅重放法学负责人批准的算术规则。规则、步骤或输入未批准时 fail closed。
- `engine/adapters/consistency.py`：检查结果使用的证据、法源、金额快照和文书必填字段是否与案件包一致。
- `engine/adapters/t1_contract.py`：按 API-01 将 T3 保真数据投影为 `CaseCreate` / `case.facts.v1` / T1 任务结果，严格区分服务端 ID 与数据集 ID。
- `skills/legal/case/fact_extract.py`：金额提取支持无货币前缀的“42万元/4200元”，输出标准金额类型候选，但仍保持 `candidate`。

## 三案选择及边界

| 演示案 | 原素材 | 覆盖争点 | 当前阻断项 |
| --- | --- | --- | --- |
| A 帮助行为案 | 合成案例003 | 丙的风险认识形成、引流阶段、帮信与诈骗共犯、员工认识能否归属于单位 | 缺第二份证据材料；候选路径、行为时法、量刑和文书未会签 |
| B 资金处置案 | 合成案例010 | 犯罪所得形成后接收/取现/转交、帮信与掩隐、单位归责、五类金额口径 | 缺第二份证据材料；2024年行为与2025年新解释的时间适用待核；量刑和文书未会签 |
| C 单位涉外案 | 合成案例004 | 风险逐级报告、负责人决定、单位归责、形式制度与实际执行、诈骗共犯排除、涉外连接点 | 境外行为地/结果地/资金节点不足；缺第二份证据材料；量刑和文书未会签 |

案例003和004来自同一组事实的不同分支，用来验证“未上报/私自绕过”与“逐级上报/负责人决定继续”对单位归责结果的影响。它们不能被当作两个互相独立的真实判决样本。

## 字段字典

| 字段 | 含义 | T1/T2 使用要求 |
| --- | --- | --- |
| `case_id` / `case_code` | T3 数据集稳定标识和演示简称 | 分别写入 `metadata.datasetCaseId` / `metadata.datasetCaseNo`；绝不冒充 T1 `CaseView.id` |
| `documents[].role` | `case_material` 是案件材料；`benchmark_annotation` 是待核标注 | 标注绝不能计入支持定罪的证据数 |
| `documents[].sha256` / `source_version` | 原文件内容身份 | 解析结果、事实快照应绑定该版本 |
| `actors[]` | 人或单位及其材料角色 | 角色不等于主从犯等法律身份 |
| `relationships[]` | 任职、汇报、控制、通信等客观关系 | 只画事实关系，不自动推出罪责 |
| `evidence[].locator` | 原 DOCX 段落或 PDF 页码位置 | T2 提供回跳；T1 保留 `documentId + locator` |
| `facts[].stage` | 行为在犯罪链条中的时间/阶段 | 同一行为人不同阶段不得合并 |
| `facts[].verification_status` | `candidate`、`baseline_asserted`、`confirmed`、`rejected`、`conflicted` | 只有人工操作可升级为 `confirmed` |
| `amounts[].kind` | 金额口径，不同口径不能直接互换 | 页面同时显示标签、数值、币种、证据和确认状态 |
| `analyses.*.candidate_paths[]` | 候选、替代或排除路径 | `baseline_position` 不是审核决定；支持和相反证据并列展示 |
| `legal_source_ids` | 案件可能涉及的法源 ID | 结果必须保存具体 ID、版本和查询日期 |
| `source_version_binding` | 行为时与当前复核时来源分组 | 日期过滤不能替代刑法时间效力判断 |
| `sentencing.actor_baselines[]` | 原标注中的结果基准及待核规则入口 | `benchmark_disposition` 只用于比对，不能作为计算输出 |
| `document_fields.required` | 文书模板最小字段 | 缺字段或含 `【待补充】` 时不得进入批准状态 |
| `missing_items[]` | 缺证据、冲突、来源或审核事项 | `severity=blocking` 时页面应显示阻断而非空结果 |

金额类型统一使用：`account_total_flow`（账户总流水）、`fraud_related_inflow`（涉诈流入）、`payment_settlement`（支付结算）、`crime_amount`（犯罪数额）、`crime_proceeds`（犯罪所得/单位获利）、`personal_participation`（个人参与数额）、`personal_profit`（个人获利）、`restitution`（退赔/退缴）。无法判断口径时用 `unclassified_amount` 并保持 `candidate`。

## 法源版本表

| source id | 版本/日期 | 三案用途 | 官方来源 |
| --- | --- | --- | --- |
| `cn-criminal-law-287-2-current` | 当前核对文本；条文自2015-11-01施行 | 帮信构成、法定刑、单位犯罪、竞合 | [刑法全文](https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/bgt/art/2025/art_890f1333b6284c3cbb225c3cd2647c4b.html) |
| `cn-criminal-law-266-current` | 当前核对文本 | 诈骗罪及共犯候选路径的实体法入口 | [刑法全文](https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/bgt/art/2025/art_890f1333b6284c3cbb225c3cd2647c4b.html) |
| `cn-criminal-law-312-current` | 当前核对文本 | 掩隐构成、法定刑、单位犯罪 | [刑法全文](https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/bgt/art/2025/art_890f1333b6284c3cbb225c3cd2647c4b.html) |
| `cn-criminal-law-6-7-current` | 当前核对文本 | 属地/属人连接点 | [刑法全文](https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/bgt/art/2025/art_890f1333b6284c3cbb225c3cd2647c4b.html) |
| `cn-cybercrime-interpretation-2019-11-12` | 法释〔2019〕15号，2019-11-01施行 | 明知、相反证据、情节严重 | [最高法发布页](https://www.court.gov.cn/fabu/xiangqing/193711.html) |
| `cn-telefraud-opinion-2016-common-crime` | 法发〔2016〕32号 | A/C行为期间诈骗共犯界分 | [最高法发布页](https://www.court.gov.cn/fabu/xiangqing/33361.html) |
| `cn-helping-opinion-2025-4-9` | 法发〔2025〕12号，2025-07-22 | 当前复核中的明知、帮信/掩隐/共犯界分和跨境从严因素 | [最高法发布页](https://www.court.gov.cn/zixun/xiangqing/472121.html) |
| `cn-concealment-interpretation-2015-2021` | 2021修正版本，至2025-08-25 | B案2024年行为时旧规则候选 | [最高法公报](https://gongbao.court.gov.cn/Details/67c58e283e9987cf41af558e71e3e5.html) |
| `cn-concealment-interpretation-2025-1-12` | 法释〔2025〕13号，2025-08-26施行 | B案当前复核、方法/明知/情节严重/事前通谋/单位 | [最高法发布页](https://www.court.gov.cn/zixun/xiangqing/474141.html) |

其中 2025 年掩隐解释明确自 2025-08-26 施行并同时废止 2015 年解释和 2021 年修改决定。适配器会报告 `effective`、`not_yet_effective` 或 `expired`，但不会自行决定新旧司法解释对既往行为的法律适用。

## T1 API-01 接口映射（已对齐）

`build_t1_case_create()` 输出 T1 `CaseCreate`，不输出 `caseId`；创建后必须使用 T1 返回的 `CaseView.id`。上传前事件文档使用 `doc-pending-upload`，上传后传入 `{T3 document_id: DocumentView.id}` 映射重建 metadata；不得重建解析任务。

```json
{
  "title": "支付企业组织转移已形成涉诈资金案",
  "jurisdiction": "CN",
  "asOfDate": "2026-09-14",
  "metadata": {
    "datasetCaseNo": "B",
    "datasetCaseId": "demo-case-b-proceeds",
    "relations": {
      "actors": [],
      "organizations": [],
      "accounts": [],
      "events": [],
      "links": []
    }
  }
}
```

`build_t1_fact_view()` 只输出 `id/key/value/locator/sourceDocumentId`，不把条级 `verification_status` 或 `source_version` 写入 FactItem。`confirmed` 投影必须显式提供已经人工确认的 item ID；不得用案件级确认批量提升 T3 条级状态。

`map_sentencing_result_to_t1()` 将 T3 `blocked` 保存为 `content.analysisStatus`，将 T1 TaskView 顶层状态映射为 `waiting_review`，并保留 `blockers[].code/path/message`。`resultVersion` 由 T1 `ResultRef.version` 生成，T3 结果内不伪造。

### 固定转换规则

- `caseId`：仅使用 T1 服务端 `CaseView.id`。
- `documentId` / `sourceDocumentId`：仅使用上传后的 `DocumentView.id`；证据定位转为 `paragraph:n` / `page:n` 字符串。
- 个人写入 `relations.actors[]`；单位写入 `relations.organizations[]`，其 `actorId` 保留 T3 统一主体引用。
- T3 `relationships[]` 写入可扩展 metadata 的 `relations.links[]`，避免任职、汇报、控制关系丢失。
- `asOfDate` 表示法律分析基准日；行为日期仍保存在 events / `conduct_period`。

## Engine 内部接入契约

T3 只接入 Engine 现有调用链，不新建公开 API。任务分派优先读取 `metadata.task_type` / `metadata.operation`，否则读取 `result_type`。

### `document.parse.v1` / `DocumentParseRunner`

上传成功后由 T1 自动建立解析任务。T1 内部调用 Engine 时提供真实 `DocumentView.id`和已取出的文档内容；浏览器或 T2 不传 `storageKey`。

```json
{
  "result_type": "document.parse.v1",
  "case_id": "case-server-id",
  "metadata": {
    "document": {
      "documentId": "doc-server-id",
      "filename": "material.docx",
      "content_base64": "..."
    }
  }
}
```

输出保持 `document.parse.v1`：

```json
{
  "schemaVersion": "document.parse.v1",
  "documentId": "doc-server-id",
  "paragraphs": [{"paragraph": 1, "locator": "paragraph:1", "text": "...", "style": null}],
  "tables": [],
  "pages": [],
  "text": "...",
  "warnings": []
}
```

DOCX 使用 `paragraph:n` / `table:n`，PDF 使用 `page:n`。缺少 ID、文件名或内容时返回结构化非重试错误。

### `sentencing.calculate` / `SentencingRunner`

三案基准模式输入：

```json
{
  "result_type": "sentencing.calculate",
  "case_id": "case-server-id",
  "metadata": {
    "sentencing": {
      "datasetCaseId": "demo-case-b-proceeds",
      "actorId": "actor-b-li"
    }
  }
}
```

会签后也可在 `metadata.sentencing` 中显式传入 `parameters[]` 和 `rule`。输出中 `caseId` 仍是 T1 服务端 ID，`datasetCaseId` 是 T3 数据集 ID。缺少已确认事实或已批准规则时：

```json
{
  "caseId": "case-server-id",
  "datasetCaseId": "demo-case-b-proceeds",
  "actorId": "actor-b-li",
  "analysisStatus": "blocked",
  "termMonths": null,
  "blockers": [{"code": "rule_not_approved", "path": "rule.legal_review_status", "message": "..."}],
  "humanReviewRequired": true
}
```

Worker 必须完整保存该 content，并将任务置为 `waiting_review`；不返回 500，不丢弃 `blockers`。

### `search_legal_sources()` / 内部同步路由

T1 使用 `X-Service-Token` 调用 `POST /internal/v1/sources/search`，公开 `/v1/sources/search` 由 T1 转发，不进入任务 Worker。

```json
{
  "query": "2025掩隐解释",
  "asOfDate": "2026-09-14",
  "sourceIds": [],
  "jurisdiction": "CN",
  "topK": 5
}
```

输出 `status=ok|unsupported_query`、`documents[]`、`effective_status`、`checked_as_of` 和 `warnings[]`。未覆盖查询是可读业务结果 `unsupported_query`，不是系统异常。

### 统一错误格式

Runner 输入错误使用：

```json
{
  "code": "document_parse_input_invalid",
  "path": "metadata.document",
  "message": "one of content_base64, text, or pages is required",
  "retryable": false
}
```

该 JSON 写入 Engine `error_message`，`code` 同时写入 `error_code`。未覆盖案件返回 `sentencing_case_unsupported`；此类输入错误不重试。

## PR5 文档回填依赖

PR5 合并后，上传和事件定位的固定顺序是：

1. `POST /v1/cases/{caseId}/documents`。
2. 读取返回的真实 `DocumentView.id` 和自动创建的 `parseTaskId`；只轮询该任务。
3. `PATCH /v1/cases/{caseId}/metadata/relations/events/{eventId}/document`，请求体为 `{"documentId":"...","locator":"paragraph:3"}`。
4. 使用返回的最新 `CaseView`。

PR5 未合并前，T3 只生成 `doc-pending-upload`，不自行新建替代公开接口。

## T2 展示要求

- 事实卡展示 `stage`、`verification_status`、证据定位；`baseline_asserted` 使用“待法核基准”，不能显示“已确认”。
- 候选路径同时显示 `supporting_evidence_ids` 与 `contrary_evidence_ids`。
- B 案同时显示账户总流入 42 万、涉诈 20 万、普通结算 22 万、公司获利 1.2 万、个人获利 4200 和退缴 1.62 万，禁止用账户总流入代替犯罪所得。
- C 案合规页使用事实清单，不显示合规分数；涉外页明确哪些连接点只是 `candidate`。
- 量刑返回 `blocked` 时展示待确认项，不展示 `benchmark_disposition` 为系统预测。

## 法学负责人会签清单

- [ ] 确认三案选取和原案号/合成素材之间的说明准确。
- [ ] 为每案补足至少第二份案件证据材料及定位。
- [ ] 逐项确认事实、反证和证据冲突。
- [ ] 确认 A/C 的帮信—诈骗共犯界分及单位归责。
- [ ] 确认 B 的犯罪所得形成时间、掩隐—帮信界分和单位归责。
- [ ] 确认 B 案新旧司法解释的时间适用。
- [ ] 确认每案金额口径，不把流水、犯罪数额、所得和获利混用。
- [ ] 提供每名主体的规则版本、计算步骤、适用条件和法源；不得只给最终区间。
- [ ] 确认三案文书类型、模板正文、字段和缺项处理。
