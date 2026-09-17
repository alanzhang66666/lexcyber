# T3 三案数据、法源与计算交接说明

版本：2026-09-17（终版清单已部分会签，量刑与文书仍阻断）

## 交付范围

本次实现提供 T3 内部能力，不新增公开 API，也不替 T1 保存任务/结果或替 T2决定页面法律文案：

- `demo_cases/three_case_demo/`：A/B/C 三案机器可读样例、原文件路径和哈希、事实—证据—阶段—金额—候选路径映射。
- `engine/adapters/case_bundle.py`：加载单案、检查重复编号/缺文件/引用完整性/审批状态。
- `engine/adapters/sources.py`：仅检索三案涉及的十条版本化官方法源记录；超出范围明确返回 `unsupported_query`。
- `engine/adapters/sentencing.py`：仅重放法学负责人批准的算术规则。规则、步骤或输入未批准时 fail closed。
- `engine/adapters/consistency.py`：检查结果使用的证据、法源、金额快照和文书必填字段是否与案件包一致。
- `engine/adapters/t1_contract.py`：按 API-01 将 T3 保真数据投影为 `CaseCreate` / `case.facts.v1` / T1 任务结果，严格区分服务端 ID 与数据集 ID。
- `skills/legal/case/fact_extract.py`：金额提取支持无货币前缀的“42万元/4200元”，输出标准金额类型候选，但仍保持 `candidate`。

## 三案选择及边界

| 演示案 | 原素材 | 覆盖争点 | 当前阻断项 |
| --- | --- | --- | --- |
| A 帮助行为案 | 合成案例011（改） | 冯某概括明知、GOIP帮助阶段、诈骗共犯排除、员工认识能否归属于单位 | 支付结算金额口径为三级待核；量刑计算规则和文书模板结构未会签 |
| B 资金处置案 | 合成案例009（改）；终版另要求042改编 | 黄某在上游既遂前提供账户的帮信路径、资金形成时点、帮信与掩隐界分、单位归责 | 文件夹缺042输入材料与法学标注；009量刑文本内部不一致；计算规则和模板未会签 |
| C 单位涉外案 | 合成案例016 | 风险逐级报告、管理层决定继续、单位归责、诈骗共犯排除、境内外管辖连接点 | 七项境外连接点待核；11.8万/9.8万违法所得口径、量刑计算规则和模板未会签 |

2026-09-17 更新保留 `case_id` 和 A/B/C 外部键稳定，只替换包内素材、演员、证据、事实、金额与路径。输入材料是案件证据；法学标注和终版说明只记录核验结论，不作为证据。B 的 042 摘要不能替代缺失的原始输入材料和法学标注。

## 字段字典

| 字段 | 含义 | T1/T2 使用要求 |
| --- | --- | --- |
| `case_id` / `case_code` | T3 数据包稳定标识和 A/B/C 简称 | `case_code` 写入 PR5 固定的 `metadata.datasetCaseId`，`case_id` 保存为 `metadata.t3BundleId`；绝不冒充 T1 `CaseView.id` |
| `documents[].role` | `case_material` 是案件材料；`benchmark_annotation` / `legal_review_summary` 是核验记录 | 标注和说明绝不能计入支持定罪的证据数 |
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
| `cn-sentencing-guidance-2024-2` | 法〔2024〕132号，2024-07-01起试行一年 | 帮信罪量刑起点、基准刑、罚金和缓刑框架；不等于已批准计算规则 | [深圳市盐田区人民法院发布页](https://www.shenpan.gov.cn/sfgg/zywj/content/post_1398982.html) |
| `cn-concealment-interpretation-2015-2021` | 2021修正版本，至2025-08-25 | B案2024年行为时旧规则候选 | [最高法公报](https://gongbao.court.gov.cn/Details/67c58e283e9987cf41af558e71e3e5.html) |
| `cn-concealment-interpretation-2025-1-12` | 法释〔2025〕13号，2025-08-26施行 | B案当前复核、方法/明知/情节严重/事前通谋/单位 | [最高法发布页](https://www.court.gov.cn/zixun/xiangqing/474141.html) |

其中 2025 年掩隐解释明确自 2025-08-26 施行并同时废止 2015 年解释和 2021 年修改决定。适配器会报告 `effective`、`not_yet_effective` 或 `expired`，但不会自行决定新旧司法解释对既往行为的法律适用。

## T1 API-01 接口映射（已对齐）

`build_t1_case_create()` 输出 T1 `CaseCreate`，不输出 `caseId`；创建后必须使用 T1 返回的 `CaseView.id`。上传前事件文档使用 `doc-pending-upload`，上传后通过 PR5 PATCH 接口逐事件回填真实 `DocumentView.id`；不得重建解析任务。

```json
{
  "title": "支付科技公司员工私自提供企业账户帮助行为案",
  "jurisdiction": "CN",
  "asOfDate": "2026-09-17",
  "metadata": {
    "datasetCaseId": "B",
    "t3BundleId": "demo-case-b-proceeds",
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

T3 只接入 Engine 现有调用链，不新建公开 API。任务分派使用 T1 已固定的 `metadata.taskType`。

### `document.parse.v1` / `DocumentParseRunner`

上传成功后由 T1 自动建立解析任务。浏览器或 T2 只提交文件，不传 `storageKey`；T1 在内部执行包的 metadata 顶层注入真实 `documentId` / `storageKey` / `filename` / `contentType`，Engine 的 `DocumentParseRunner` 再从 MinIO 回读字节。

```json
{
  "result_type": "workflow.output",
  "case_id": "case-server-id",
  "metadata": {
    "taskType": "document.parse",
    "documentId": "doc-server-id",
    "storageKey": "objects/sha256",
    "filename": "material.docx",
    "contentType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "schemaVersion": "document.parse.v1"
  }
}
```

输出保持 `document.parse.v1`：

```json
{
  "schemaVersion": "document.parse.v1",
  "taskType": "document.parse",
  "documentId": "doc-server-id",
  "format": "docx",
  "paragraphs": [{"paragraph": 1, "locator": "paragraph:1", "text": "...", "style": null}],
  "tables": [],
  "pages": [],
  "text": "...",
  "warnings": [],
  "missing": [],
  "errors": []
}
```

DOCX 使用 `paragraph:n` / `table:n`，PDF 使用 `page:n`。缺少对象存储键、文件为空或解析失败时，沿用 T1 错误码 `DOCUMENT_PARSE_FAILED`；超时为 `DOCUMENT_PARSE_TIMEOUT`。

### `sentencing.calculate` / `SentencingRunner`

三案基准模式输入：

```json
{
  "result_type": "workflow.output",
  "case_id": "case-server-id",
  "metadata": {
    "taskType": "sentencing.calculate",
    "sentencing": {
      "datasetCaseId": "B",
      "actorId": "actor-b-huang"
    }
  }
}
```

会签后也可在 `metadata.sentencing` 中显式传入 `parameters[]` 和 `rule`。输出中 `caseId` 是 T1 服务端 ID，`datasetCaseId` 是 A/B/C，`t3BundleId` 是 T3 内部稳定 ID。缺少已确认事实或已批准规则时：

```json
{
  "caseId": "case-server-id",
  "datasetCaseId": "B",
  "t3BundleId": "demo-case-b-proceeds",
  "actorId": "actor-b-huang",
  "analysisStatus": "blocked",
  "termMonths": null,
  "blockers": [{"code": "rule_not_approved", "path": "rule.legal_review_status", "message": "..."}],
  "humanReviewRequired": true
}
```

Worker 必须完整保存该 content，并将任务置为 `waiting_review`；不返回 500，不丢弃 `blockers`。会签前 `SENTENCING_ENABLED=false`，T1 公开入口仍返回 501。

### `search_legal_sources()` / 内部同步路由

T1 使用 `X-Service-Token` 调用 `POST /internal/v1/sources/search`，公开 `/v1/sources/search` 由 T1 转发，不进入任务 Worker。

```json
{
  "query": "2025掩隐解释",
  "as_of_date": "2026-09-17",
  "jurisdiction": "CN",
  "top_k": 5
}
```

内部响应严格使用 T1 `SourceSearchResponse.items[]`，每项为 `source_id/locator/title/quote/version/jurisdiction`。未覆盖查询返回空 `items`。会签前 `LEGAL_SOURCE_SEARCH_ENABLED=false`，路由仍返回 `501 SOURCE_SEARCH_UNAVAILABLE`。

### 统一错误格式

`sentencing.calculate` 输入错误使用：

```json
{
  "code": "DATASET_CASE_ID_MISSING",
  "path": "metadata.sentencing.datasetCaseId",
  "message": "T3 dataset case id is required",
  "retryable": false
}
```

该 JSON 写入 Engine `error_message`，`code` 同时写入 `error_code`。未覆盖案件返回 `SENTENCING_CASE_UNSUPPORTED`；此类输入错误不重试。文档解析继续使用 T1 已固定的错误码。

## PR5 文档回填依赖

PR5 合并后，上传和事件定位的固定顺序是：

1. `POST /v1/cases/{caseId}/documents`。
2. 读取返回的真实 `DocumentView.id` 和自动创建的 `parseTaskId`；只轮询该任务。
3. `PATCH /v1/cases/{caseId}/metadata/relations/events/{eventId}/document`，请求体为 `{"documentId":"...","locator":"paragraph:3"}`。
4. 使用返回的最新 `CaseView`。

PR5 已合并。创建案件时 T3 先生成 `doc-pending-upload`，上传后通过上述 PATCH 逐事件回填，不新建替代公开接口。

## T2 展示要求

- 事实卡展示 `stage`、`verification_status`、证据定位；`baseline_asserted` 使用“待法核基准”，不能显示“已确认”。
- 候选路径同时显示 `supporting_evidence_ids` 与 `contrary_evidence_ids`。
- B 案 009 同时显示账户总流入 42 万、涉诈 20 万、普通结算 22 万、黄某获利及退缴 4200 元；不得虚构公司获利，也不得用账户总流入代替涉诈金额。
- C 案合规页使用事实清单，不显示合规分数；涉外页明确哪些连接点只是 `candidate`。
- 量刑返回 `blocked` 时展示待确认项，不展示 `benchmark_disposition` 为系统预测。

## 法学负责人会签清单

- [x] 确认 A=011（改）、B=009+042改编、C=016 的基准组合；代码保留稳定 A/B/C 外部键。
- [x] 逐项确认 A、009、C 的主要事实、反证和候选路径。
- [x] 确认 A/C 的帮信—诈骗共犯界分及单位归责方向。
- [ ] 补充 B 案 042 改编终稿输入材料和法学标注，摘要不能替代原材料。
- [ ] 解决 A 的支付结算金额三级待核项、C 的境外连接点及违法所得口径。
- [ ] 复核 009 量刑文字中的区间冲突和全部金额口径，不自行择取结果。
- [ ] 提供每名主体的规则版本、计算步骤、适用条件和法源；不得只给最终区间。
- [ ] 确认三案文书类型、模板正文、字段和缺项处理。
