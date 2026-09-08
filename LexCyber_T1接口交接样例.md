# LexCyber T1 接口交接样例（T2 / T3 共用）

- 依据：技术分工0906.md。
- 来源：2026-09-08 本地 Compose（`http://127.0.0.1:18080`）实测，不是建议稿。
- 用途：第一轮「案件 → 上传材料 → 解析任务 → 解析结果」。
- 约定：上传成功即带 `parseTaskId`。T2 / T3 只轮询，不要再 `POST /v1/tasks` 建解析任务。正文只从 `/result` 读。
- 约定：T2 / T3 **不要**自己传 `storageKey`。服务端从属主材料覆盖；客户端伪造键无效。

本轮实测 ID（最近一次本地 closeout）：

| 字段 | 值 |
| --- | --- |
| caseId | `case-17bcd846f38d49fd` |
| documentId | `doc-2908dc3ad1474fff` |
| parseTaskId | `90f80f51-c799-49b5-96b7-056b3f573c5c` |

下文 JSON 正文仍保留更早一次实测（`case-75a7f5b18e4e4361` / `doc-925c3fe9100f4fe4` / `9bc96484-48b3-40da-a98e-a0d1b0b73d29`），结构未变；对接请以表内最新 ID 为准。不要把口令或 API key 写进本文件。

## 一、实现范围

| 内容 | 现状 |
| --- | --- |
| 公开服务 | Java `/v1`；Engine 执行 |
| 案件、材料 | 已持久化，Bearer + 属主校验 |
| 上传后解析 | 上传即建 `document.parse` 任务 |
| 任务结果 | 外层 `workflow.output`；`content.schemaVersion=document.parse.v1` |
| PDF/DOCX | Engine 从 MinIO 回读字节后走现有 Skill |

## 二、给 T2：请求、响应样例

登录复用 `POST /v1/auth/login`（或 `POST /v1/auth/register`），之后：

```http
Authorization: Bearer <token>
```

未带 Bearer 时 `POST /v1/cases` 返回 401：

```json
{
  "code": "UNAUTHORIZED",
  "message": "session required",
  "traceId": "f05ff067-7839-42f3-9845-f39561ee8fa4",
  "retryable": false
}
```

保留任务同样要登录。未带 Bearer 时 `POST /v1/tasks` 实测 401（本地 closeout）：

`metadata.taskType=document.parse`（即使带客户端 `storageKey`）：

```json
{ "code": "UNAUTHORIZED", "message": "session required", "retryable": false }
```

`metadata.taskType=model.probe`：

```json
{ "code": "UNAUTHORIZED", "message": "session required", "retryable": false }
```

### 1. 创建案件

```http
POST /v1/cases
Content-Type: application/json
Authorization: Bearer <token>
```

请求：

```json
{
  "title": "测试案例 001",
  "jurisdiction": "CN",
  "asOfDate": "2026-09-06",
  "metadata": {
    "datasetCaseNo": "001",
    "isDevelopmentSample": true
  }
}
```

实测 `201 Created`：

```json
{
  "id": "case-75a7f5b18e4e4361",
  "title": "测试案例 001",
  "jurisdiction": "CN",
  "asOfDate": "2026-09-06",
  "metadata": {
    "datasetCaseNo": "001",
    "isDevelopmentSample": true
  },
  "createdAt": "2026-09-08T09:29:42.17171Z",
  "updatedAt": "2026-09-08T09:29:42.17171Z"
}
```

`GET /v1/cases/case-75a7f5b18e4e4361` 返回同一结构。

`GET /v1/cases?page=0&size=20` 实测：

```json
{
  "items": [
    {
      "id": "case-75a7f5b18e4e4361",
      "title": "测试案例 001",
      "jurisdiction": "CN",
      "asOfDate": "2026-09-06",
      "metadata": {
        "datasetCaseNo": "001",
        "isDevelopmentSample": true
      },
      "createdAt": "2026-09-08T09:29:42.17171Z",
      "updatedAt": "2026-09-08T09:29:42.17171Z"
    }
  ],
  "page": 0,
  "size": 20,
  "total": 1
}
```

跨用户访问同一案件返回 404 `CASE_NOT_FOUND`（「案件不存在或不可访问」）。

### 2. 上传材料并自动创建解析任务

```http
POST /v1/cases/case-75a7f5b18e4e4361/documents
Authorization: Bearer <token>
Idempotency-Key: upload-demo-4302
Content-Type: multipart/form-data
```

表单字段：`file`（必填）、`role`（必填，`input` 或 `annotation`）。

实测 `201 Created`：

```json
{
  "id": "doc-925c3fe9100f4fe4",
  "caseId": "case-75a7f5b18e4e4361",
  "filename": "案情材料.docx",
  "contentType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "size": 1071,
  "role": "input",
  "parseStatus": "queued",
  "parseTaskId": "9bc96484-48b3-40da-a98e-a0d1b0b73d29",
  "createdAt": "2026-09-08T09:29:42.244528Z"
}
```

- 上传成功表示文件可恢复，材料记录与解析任务已登记。
- T2 / T3 拿到 `parseTaskId` 后只轮询，不要再手工建解析任务。
- 不要传客户端 `storageKey`。若仍手工 `POST /v1/tasks` 且 `taskType=document.parse`，服务端用属主材料覆盖 `storageKey` 与 `caseId`（客户端伪造键无效）。
- 同一用户、案件、`Idempotency-Key` 且内容相同：返回原材料及原任务。
- 同 Key、内容不同：`409 IDEMPOTENCY_CONFLICT`（「相同幂等键已用于不同内容的上传」）。
- 非 PDF/DOCX：`415 UNSUPPORTED_DOCUMENT_TYPE`（「仅支持 PDF 或 DOCX 材料」）。
- `annotation` 会解析正文，不得当作已确认事实。

### 3. 材料列表与详情

`GET /v1/cases/case-75a7f5b18e4e4361/documents?role=input&page=0&size=20` 返回 `items/page/size/total`。

`GET /v1/documents/doc-925c3fe9100f4fe4` 刷新后材料仍在。`parseStatus` 跟随关联任务；刚上传可能是 `queued`，完成后与任务状态一致。正文不要从材料详情读。

跨用户：`404 DOCUMENT_NOT_FOUND`。

### 4. 查询解析状态

```http
GET /v1/tasks/9bc96484-48b3-40da-a98e-a0d1b0b73d29
```

T2 每 2 秒轮询。不要造进度百分比。公开状态：

```text
queued / running / completed / waiting_review / failed / timed_out / rejected
```

实测完成后：

```json
{
  "id": "9bc96484-48b3-40da-a98e-a0d1b0b73d29",
  "requestId": "6a47904c-0fb0-49d2-b382-14bb55546dee",
  "executionId": "1ae033e1-16b0-4904-8d57-94da14f8b9d9",
  "caseId": "case-75a7f5b18e4e4361",
  "status": "completed",
  "currentStage": "output",
  "result": {
    "resultId": "b106bb11-dc86-4d69-9f6c-bde2f12c7707",
    "version": 1,
    "type": "workflow.output",
    "contentHash": "21fb252e16b85cfebb1947e585cdc7df343da23bd958a65f19bcd80e11b778ea",
    "sourceRefs": []
  },
  "errorCode": null,
  "error": null,
  "createdAt": "2026-09-08T09:29:42.244528Z",
  "updatedAt": "2026-09-08T09:29:44.608629Z"
}
```

跨用户查该任务：`404 CASE_NOT_FOUND`。

### 5. 读取解析结果

```http
GET /v1/tasks/9bc96484-48b3-40da-a98e-a0d1b0b73d29/result
```

实测：

```json
{
  "resultId": "b106bb11-dc86-4d69-9f6c-bde2f12c7707",
  "version": 1,
  "type": "workflow.output",
  "contentHash": "21fb252e16b85cfebb1947e585cdc7df343da23bd958a65f19bcd80e11b778ea",
  "content": {
    "schemaVersion": "document.parse.v1",
    "taskType": "document.parse",
    "documentId": "doc-925c3fe9100f4fe4",
    "format": "docx",
    "text": "测试案例 001\n以下为开发样例正文。",
    "pages": [],
    "paragraphs": [
      {
        "paragraph": 1,
        "text": "测试案例 001",
        "style": "Normal",
        "locator": "paragraph:1"
      },
      {
        "paragraph": 2,
        "text": "以下为开发样例正文。",
        "style": "Normal",
        "locator": "paragraph:2"
      }
    ],
    "tables": [
      {
        "table": 1,
        "rows": [
          ["项目", "内容"],
          ["材料类型", "开发样例"]
        ],
        "locator": "table:1"
      }
    ],
    "warnings": [],
    "missing": [],
    "errors": []
  }
}
```

外层 `type` 仍是 `workflow.output`。业务类型看 `content.taskType` / `content.schemaVersion`。

### 6. 失败和重试

损坏 PDF 实测任务：

```json
{
  "status": "failed",
  "currentStage": "document_parsing",
  "result": null,
  "errorCode": "DOCUMENT_PARSE_FAILED",
  "error": "无法解析该文件，请检查文件是否损坏或加密"
}
```

`POST /v1/tasks/{taskId}/retry` 实测 `202`：同一 `id` 和 `requestId`，新 `executionId`，`status=queued`，`currentStage=retry_requested`。

| 场景 | HTTP / 任务状态 | 错误码 |
| --- | --- | --- |
| 未登录 | 401 | UNAUTHORIZED |
| 案件/材料不存在或无权限 | 404 | CASE_NOT_FOUND / DOCUMENT_NOT_FOUND |
| 不支持的格式 | 415 | UNSUPPORTED_DOCUMENT_TYPE |
| 同 Key 不同内容 | 409 | IDEMPOTENCY_CONFLICT |
| 解析失败 | 任务 failed | DOCUMENT_PARSE_FAILED |
| 解析超时 | 任务 timed_out | DOCUMENT_PARSE_TIMEOUT |

## 三、给 T3：内部调用

T3 仍复用：

```python
skills.common.document.parse_docx.execute(payload)
skills.common.document.parse_pdf.execute(payload)
```

字节由服务端从 MinIO 回读后以 `content_base64` 传入。T2 / T3 不传 `storageKey`、不直连 Engine、不直连对象存储。上传已自动创建 `parseTaskId`，只轮询公开任务接口。

统一结果已含 `locator`（`paragraph:1` / `table:1` / `page:1`）。DOCX 不伪造页码。PDF 表格抽取未宣称支持。

内部 API 用 snake_case，公开 API 用 camelCase。内部请求带 `X-Service-Token`。

## 四、本轮已核对

- 上传后回读存储文件，不再传空文本。
- 完整保存 paragraphs / tables / locators。
- `metadata.taskType=document.parse` 分发，不靠 query 猜类型。
- 未登录创建 `document.parse` / `model.probe` → 401 `UNAUTHORIZED`。
- 客户端 `storageKey` 由服务端按属主材料覆盖。
- 契约在 `contracts/public-api.yaml`，类型在 `web/src/api-types.ts`。

事实确认、量刑、法源检索不在本交接范围内。检索口已留：`POST /v1/sources/search` 未接通时为 `501 SOURCE_SEARCH_UNAVAILABLE`。
