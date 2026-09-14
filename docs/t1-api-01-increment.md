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
| `locator` | **现有复用** | `FactItem.locator`；`document.parse.v1` 的 `paragraphs[].locator` / `tables[].locator` |
| `parseTaskId` | **现有复用** | `DocumentView.parseTaskId`；只轮询，不重建 |
| `factId` | **现有复用** | `FactItem.id`；`PUT` 省略时服务端发 UUID |
| `verificationStatus` | **尚未落地**（条级） | 条级待核枚举本轮不入库。案件级复用 `FactView.status`：`draft` / `confirmed` |
| `actorId` | **本轮新增（约定）** | 写入 `CaseView.metadata.relations.actors[]`，无新列 |
| `organizationId` | **本轮新增（约定）** | `metadata.relations.organizations[]` |
| `accountId` | **本轮新增（约定）** | `metadata.relations.accounts[]` |
| `eventId` / `stage` | **本轮新增（约定）** | `metadata.relations.events[]` |
| `sourceVersion` | **尚未落地** | 分析/法源绑定版本等 T3 结果 JSON；不要当公开列。`SourceRef.version` 仍是检索占位 |
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
    "datasetCaseNo": "A",
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

`GET /v1/cases/{caseId}` 原样回传 `metadata`。`documentId` 在实际上传后换成真实 id；导入脚本不要为此再建解析任务。

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

`items[].id` 即 `factId`。`status=confirmed` 后 `PUT` 仍是 `409 FACTS_CONFIRMED`。条级 `verificationStatus`、模块结果 `sourceVersion` 本轮不要写进 `FactItem`——Jackson 会丢掉未知字段。

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

- 接通 `/v1/sources/search` 与 `sentencing.calculate`（保持 501）。
- 合规 / 定罪 / 量刑 / 文书草稿的正式结果 schema、`draftId`、模块级 `reviewStatus` 绑定。
- 条级 `verificationStatus`、一等公民 `sourceVersion`、复核表 `case_id` 列、图谱表。
