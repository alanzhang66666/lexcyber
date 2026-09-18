# API-01：三案增量契约（T1 → T2 / T3）

在现有 `CaseCreate` / `CaseView`、facts、tasks、reviews 之上的**一页增量**。不重做案件 / 上传 / 解析 / facts / 鉴权 / `model.probe`。检索与量刑适配器保持 `501`，等 T3 会签。

权威表结构仍是 `cases`、`documents`、`case_facts`、`tasks`、`result_versions`、`review_records`。三案「人—组织—账户—事件」关系放在 `metadata` 或任务结果 JSON，**本轮不建图谱平台或新大表**。

## 上传解析约定（沿用，不要改）

- 上传成功即自动建 `document.parse`，响应带 `parseTaskId`。
- T2 / 导入脚本**只轮询** `GET /v1/tasks/{parseTaskId}`，正文只读 `GET /v1/tasks/{id}/result`。
- **不要**再 `POST /v1/tasks` 建解析任务，不要传客户端 `storageKey`。
- 实测样例仍以 [`LexCyber_T1接口交接样例.md`](../LexCyber_T1接口交接样例.md) 为准。

## 字段落地标记

| 字段 | 标记 | 本轮怎么用 |
| --- | --- | --- |
| `caseId` | **现有复用** | `CaseView.id`、`DocumentView.caseId`、`FactView.caseId`、`TaskView.caseId` |
| `documentId` | **现有复用** | `DocumentView.id`；解析结果 `content.documentId` |
| 事件来源回填 | **本轮新增** | `PATCH /v1/cases/{caseId}/metadata/relations/events/{eventId}/document`；只更新该事件的 `documentId` 和可选 `locator` |
| `locator` | **现有复用** | `FactItem.locator`；`document.parse.v1` 的 `paragraphs[].locator` / `tables[].locator` |
| `parseTaskId` | **现有复用** | `DocumentView.parseTaskId`；只轮询，不重建 |
| `factId` | **现有复用** | `FactItem.id`；`PUT` 省略时服务端发 UUID |
| `verificationStatus` | **本轮新增（条级）** | `FactItem.verificationStatus`：`candidate` / `baseline_asserted` / `confirmed` / `rejected` / `conflicted`。案件级仍只看 `FactView.status`；条级 `confirmed` 不自动整包确认 |
| `actorId` | **本轮新增（约定）** | 写入 `CaseView.metadata.relations.actors[]`，无新列 |
| `organizationId` | **本轮新增（约定）** | `metadata.relations.organizations[]` |
| `accountId` | **本轮新增（约定）** | `metadata.relations.accounts[]` |
| `eventId` / `stage` | **本轮新增（约定）** | `metadata.relations.events[]` |
| `sourceVersion` | **本轮新增（约定）** | `FactItem.sourceVersion`、模块空壳 `sourceVersion`、`metadata.sourceVersionBinding` 均为可选载荷。不要当公开列。`SourceRef.version` 仍是检索占位 |
| `resultVersion` | **现有复用** | `ResultRef.version`、`ReviewRecord.resultVersion`；批准/退回必须带当前版本 |
| `reviewStatus` | **现有复用** | `ReviewRecord.status`：`pending` / `approved` / `rejected` / `superseded` |
| `ReviewRecord.caseId` | **本轮新增** | 列表/详情/决定响应都带；来自 `tasks.case_id` JOIN，不新增 `review_records.case_id` |

`organizationId` 不是登录账号。登录账号是会话里的 `accounts.id`，只用于属主过滤，不出现在三案关系 JSON。

## 复核读取（本轮已修）

`GET/POST /v1/reviews*` 与案件一样要 `Authorization: Bearer`。

- 只返回「任务 `case_id` 属于当前账号属主案件」的复核。无案任务（caseless stub）不进队列。
- 他案 / 他主 / 不存在：详情与决定一律 `404 REVIEW_NOT_FOUND`，列表省略，不泄露是否存在。
- 未登录列表不再倒出全局队列（`401 UNAUTHORIZED`）。
- `approve` / `reject` 仍绑定 `resultVersion` + `pending`；决定人用会话用户名，不接受匿名全局写。

## 样例 1：案件关系（`POST /v1/cases` 的 `metadata`）

`title` / `jurisdiction` / `asOfDate` / `metadata` 形状不变。关系只进 `metadata.relations`。系统不根据这些字段输出罪名或责任结论。

```json
{
  "title": "演示案 A（帮助行为）",
  "jurisdiction": "CN",
  "asOfDate": "2026-03-01",
  "metadata": {
    "datasetCaseId": "A",
    "relations": {
      "actors": [
        { "actorId": "actor-a-01", "label": "张某", "roleHint": "被调查人" }
      ],
      "organizations": [
        { "organizationId": "org-a-01", "label": "某支付服务商", "actorId": "actor-a-01" }
      ],
      "accounts": [
        { "accountId": "acct-a-01", "organizationId": "org-a-01", "actorId": "actor-a-01", "mask": "尾号 1024" }
      ],
      "events": [
        {
          "eventId": "evt-a-01",
          "stage": "help",
          "actorId": "actor-a-01",
          "accountId": "acct-a-01",
          "documentId": "doc-pending-upload",
          "locator": "paragraph:3",
          "occurredOn": "2026-02-11"
        }
      ]
    }
  }
}
```

`GET /v1/cases/{caseId}` 原样回传 `metadata`。`datasetCaseId` 只保存 T3 原始编号；所有公开接口的 `caseId` 都使用创建响应的 `CaseView.id`。上传后调用一次下述接口回填真实 `DocumentView.id`；同一请求重复调用安全，其他事件和元数据不变。接口要求 Bearer，并拒绝他人案件、别案材料、无此事件。导入脚本不要为此再建解析任务。

```http
PATCH /v1/cases/{caseId}/metadata/relations/events/evt-a-01/document
Authorization: Bearer <token>
Content-Type: application/json

{"documentId":"doc-925c3fe9100f4fe4","locator":"paragraph:3"}
```

`locator` 可省略，此时保留事件原定位。若创建案件时已有真实材料 ID，也可以直接在 `metadata.relations.events[]` 写入，无需调用回填接口。

## 样例 2：事实快照（现有 `FactView`）

```json
{
  "caseId": "case-75a7f5b18e4e4361",
  "schemaVersion": "case.facts.v1",
  "status": "draft",
  "items": [
    {
      "id": "fact-a-amount-01",
      "key": "payment_settlement_amount",
      "value": "128000",
      "locator": "paragraph:3",
      "sourceDocumentId": "doc-925c3fe9100f4fe4"
    }
  ],
  "updatedAt": "2026-09-08T09:30:00Z",
  "confirmedAt": null
}
```

`items[].id` 即 `factId`。`status=confirmed` 后 `PUT` 仍是 `409 FACTS_CONFIRMED`。条级 `verificationStatus` / `sourceVersion` 现可读写；未知枚举 `400`。案件级 `confirm` 不改写条级状态。

## 样例 3：复核列表项（现有 `ReviewRecord` + `caseId`）

```http
GET /v1/reviews?status=pending&page=0&size=20
Authorization: Bearer <token>
```

```json
{
  "items": [
    {
      "id": "11111111-1111-4111-8111-111111111111",
      "taskId": "9bc96484-48b3-40da-a98e-a0d1b0b73d29",
      "caseId": "case-75a7f5b18e4e4361",
      "resultVersion": 1,
      "status": "pending",
      "decision": "none",
      "actor": null,
      "comment": null,
      "authenticated": false,
      "decidedAt": null
    }
  ],
  "page": 0,
  "size": 20,
  "total": 1
}
```

决定：`POST /v1/reviews/{id}/approve` 或 `/reject`，body `{ "resultVersion": 1, "comment": "…" }`。版本或已决冲突仍是 `409`。

## 本轮不做（留给 T3 / L2 / L3）

- 接通 `/v1/sources/search` 与 `sentencing.calculate`（公开口保持 501；不要改 Compose 默认开关）。
- 合规 / 定罪分析任务与正式结果 schema；公开创建 `compliance.analyze` / `conviction.analyze` 仍 501。
- 图谱表、Word/PDF、双人会签 / 超时升级 / 正式对外归档。

## 2026-09-15 增量（会签前，不重开 501）

在 API-01 之上的 T1 独立增量。浏览器仍只打 Java `/v1`。新表只走 Flyway `V8__case_drafts.sql`。

| 项 | 约定 |
| --- | --- |
| 三案导入 | [`scripts/import_three_case_demo.py`](../scripts/import_three_case_demo.py)（可选 [`scripts/import-three-case-demo.ps1`](../scripts/import-three-case-demo.ps1)）。`POST /v1/cases` 用 `build_t1_case_create`；只上传 `role=input` 的 `case_material`；**只轮询 `parseTaskId`**；`PATCH` 回填事件 `DocumentView.id`；可选 `PUT` facts 为 `draft`，不自动 `confirm`。账号来自 `LEXCYBER_USERNAME` / `LEXCYBER_PASSWORD`，未设则注册一次性账号。`--docs-dir` 按 `archive_entry` 文件名匹配。缺材料 **fail-closed**，不再默认上传 `.t1-smoke-input.docx`；本地冒烟必须显式 `--allow-placeholder`。报告写 `.t1-three-case-import.md`。 |
| 文书草稿 | `POST/GET /v1/cases/{caseId}/drafts`、`GET/PUT .../drafts/{draftId}`。`body` 是不透明字符串。`PUT` 必须带当前 `version`，成功后 `version+1`；冲突 `409 DRAFT_VERSION_CONFLICT`。他案/他主 `404`。旧版本上的批准不自动落到新版本。 |
| 量刑 facts 门闩 | `taskType=sentencing.calculate` 且带 `caseId` 时，facts 不是 `confirmed`（含无行）→ `409 FACTS_NOT_CONFIRMED`。公开创建在开关关闭时仍先 `501`。Java 与 Engine 必须同时开；只开 Java 会建成任务再 `failed`。 |
| `ReviewRecord.module` | 不改 `review_records`。从 `tasks.metadata_json.module` 读取，没有则按 `taskType`：`document.parse`→`parse`，`sentencing.calculate`→`sentencing`，其余→`task`。`GET /v1/reviews?module=` 可选过滤。 |

## 2026-09-15 会签前独立增量（V9）

不打开 `SENTENCING_ENABLED` / `LEGAL_SOURCE_SEARCH_ENABLED`。新表/新列只走 `V9__module_states_reviews.sql`。合规/定罪 `content` 与草稿 `body` 仍是不透明载荷。

| 项 | 约定 |
| --- | --- |
| 合规 / 定罪空壳 | `GET/PUT /v1/cases/{id}/compliance` 与 `/conviction`，`POST .../confirm`。无行返回 `version=0`、`content={}`、`applicability=unknown`。`PUT` 必须带当前 `version`，成功 `version+1` 且回到 `draft`；已确认再 PUT → `409 MODULE_CONFIRMED`。`factsStale` 比较模块快照与 `case_facts.updated_at`；无事实行则 stale=false。他案/他主 `404 CASE_NOT_FOUND`。 |
| 预留任务 501 | `compliance.analyze` → `501 COMPLIANCE_UNAVAILABLE`；`conviction.analyze` → `501 CONVICTION_UNAVAILABLE`。加入 `TaskType` 与 `requiresAuth`。不接 Engine、不建任务。 |
| 条级事实状态 | `FactItem.verificationStatus` / `sourceVersion`。案件级 `POST .../facts/confirm` 行为不变。 |
| 草稿版本 | `templateVersion` / `sourceVersion`。`PUT` 升版本后，将该草稿旧 `draft_version` 上 `pending`/`approved` 复核标 `superseded`。 |
| 复核开单 / 归档 | `POST /v1/cases/{id}/reviews` 可绑草稿或模块空壳，无 `taskId` 时不写 outbox。`POST /v1/reviews/{id}/archive`。`GET /v1/reviews?archiveStatus=`。无 `task_id` 的决定只改 `review_records`。属主 JOIN `tasks.case_id` / `drafts.case_id` / `review_records.case_id`。 |
| metadata 投影 | `relations.accounts[]`、`relations.jurisdictionConnections[]`、`metadata.sourceVersionBinding`；`procedureStage` 仅当 bundle 已有才写。导入脚本 `PUT` 模块空壳，可选开一条 conviction 复核，不自动 confirm。 |

## 2026-09-18 会签前增量（模块 content 冻结 / 金额与连接点 / 导入 fail-closed）

不打开 `SENTENCING_ENABLED` / `LEGAL_SOURCE_SEARCH_ENABLED`。不建图谱表。公开分析任务仍 501。Java 仍把模块 `content` 当不透明 JSON；导入投影冻结为 `case.module.content.v1`。

| 项 | 约定 |
| --- | --- |
| 模块空壳 `content` | `build_t1_module_state` 写入 `schemaVersion=case.module.content.v1`。合规：`facts[]`（展开为带 `statement` 的对象，不再只放 fact id）、`checklist[]`、`amounts[]`、`missingItems[]`、`sourceVersionBinding`。定罪：`candidatePaths[]`（`baselinePosition`、`supportingEvidenceIds` / `contraryEvidenceIds` / `legalSourceIds`）、`amounts[]`、`missingItems[]`、`jurisdictionStatus`、`jurisdictionConnections[]`。同时写 snake_case 别名，供 T2 现有 `pick()` 读取。不是分析任务结果，不输出罪名或责任结论。 |
| 金额与法域 | 八类金额进 `metadata.amounts[]`、facts 投影（`FactItem.key` = amount `kind`）、模块 `content.amounts[]`。C 案连接点继续在 `metadata.relations.jurisdictionConnections[]`，并写入定罪 `content.jurisdictionConnections[]`。 |
| 导入缺材料 | 默认 fail-closed：无 `--docs-dir` 命中、或目录里缺 `case_material`，导入在建案前退出。`--allow-placeholder` 才上传 `.t1-smoke-input.docx`。 |

### 样例：定罪空壳 `PUT /v1/cases/{id}/conviction`

```json
{
  "applicability": "unknown",
  "sourceVersion": "{\"temporal_review_status\":\"partial_approval\"}",
  "version": 0,
  "content": {
    "schemaVersion": "case.module.content.v1",
    "applicability": "unknown",
    "candidatePaths": [
      {
        "id": "path-c-company-helping",
        "actorId": "actor-c-company",
        "label": "单位帮助信息网络犯罪活动罪",
        "baselinePosition": "selected",
        "supportingEvidenceIds": ["ev-c-02"],
        "contraryEvidenceIds": ["ev-c-12"],
        "legalSourceIds": ["cn-criminal-law-287-2-current"]
      }
    ],
    "amounts": [
      {
        "id": "amount-c-service-fee",
        "kind": "unclassified_amount",
        "label": "项目服务费",
        "value": 118000,
        "currency": "CNY",
        "verificationStatus": "confirmed",
        "classificationStatus": "pending_unlawful_income_review",
        "evidenceIds": ["ev-c-07"]
      }
    ],
    "jurisdictionConnections": [
      {
        "connectionId": "jur-c-victim",
        "type": "victim_location",
        "value": "重庆市T区存在境内被害人",
        "verificationStatus": "confirmed"
      }
    ]
  }
}
```
