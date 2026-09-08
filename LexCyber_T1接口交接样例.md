# LexCyber T1 接口交接样例（T2 / T3 共用）

- 依据：技术分工0906.docx 与仓库公开契约。
- 核对基线：`feat/t1-round1`（P0 案件 / 材料 / 自动解析）。
- 用途：第一轮「登录 → 建案 → 上传材料 → 轮询 `parseTaskId` → 读 `/result`」交接。
- 状态：下列 JSON 来自 2026-09-08 在 `http://127.0.0.1:18080` 上对 Compose v0.3（`WORKFLOW_PROFILE=stub`）的实测。未改默认 profile。Bearer token 已脱敏。

约定：上传成功即带 `parseTaskId`。T2 / T3 只轮询，不再 `POST /v1/tasks` 建解析任务。正文只从 `/result` 读。材料详情不存第二份正文。

## 一、现有实现

| 内容 | 现状 |
|---|---|
| 公开服务 | v0.3 由 Java 提供 `/v1`，Python Engine 执行 |
| 案件、材料 | Java 持久化，按 owner 鉴权；`role` = `input` \| `annotation` |
| 上传后解析 | 上传事务内自动 `TaskService.create`，`metadata.taskType=document.parse` |
| 任务结果 | 外层仍是 `type=workflow.output`；业务类型在 `content.taskType` / `content.schemaVersion` |
| PDF/DOCX | Engine 回读 MinIO，调用现有 parse skill，包装为 `document.parse.v1`（含 locator） |

T2 只调用 Java `/v1`。T3 只改 adapter / skill。

登录复用 `POST /v1/auth/login`，之后发送：

```http
Authorization: Bearer <token>
```

案件权限已覆盖关联材料、任务、结果和重试。未登录 401；跨用户按「不存在」返回 404。

## 二、给 T2：实测请求、响应

### 1. 登录

```http
POST /v1/auth/login
Content-Type: application/json
```

请求：

```json
{
  "username": "smoke_a_7857",
  "password": "<redacted>"
}
```

响应 `200`：

```json
{
  "token": "<redacted>",
  "username": "smoke_a_7857",
  "displayName": "Smoke A",
  "expiresAt": "2026-09-15T09:13:13.61477786Z"
}
```

### 2. 创建案件

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

响应 `201 Created`：

```json
{
  "id": "case-896406a64833445a",
  "title": "测试案例 001",
  "jurisdiction": "CN",
  "asOfDate": "2026-09-06",
  "metadata": {
    "datasetCaseNo": "001",
    "isDevelopmentSample": true
  },
  "createdAt": "2026-09-08T09:14:54.065968Z",
  "updatedAt": "2026-09-08T09:14:54.065968Z"
}
```

`GET /v1/cases/case-896406a64833445a` 返回同一案件结构。

`GET /v1/cases?page=0&size=20` 实测 `200`（同会话内已有更早案件，`total` 为 2）：

```json
{
  "items": [
    {
      "id": "case-896406a64833445a",
      "title": "测试案例 001",
      "jurisdiction": "CN",
      "asOfDate": "2026-09-06",
      "metadata": {
        "datasetCaseNo": "001",
        "isDevelopmentSample": true
      },
      "createdAt": "2026-09-08T09:14:54.065968Z",
      "updatedAt": "2026-09-08T09:14:54.065968Z"
    }
  ],
  "page": 0,
  "size": 20,
  "total": 2
}
```

分页为 `items/page/size/total`，page 从 0 开始。公开字段是 `asOfDate`。

### 3. 上传材料并自动创建解析任务

```http
POST /v1/cases/case-896406a64833445a/documents
Authorization: Bearer <token>
Idempotency-Key: upload-demo-utf8
Content-Type: multipart/form-data
```

表单字段：

| 字段 | 实测 | 约定 |
|---|---|---|
| file | `案情材料.docx`（1071 bytes） | 必填，仅 PDF / DOCX |
| role | `input` | 必填，只允许 `input` / `annotation` |

响应 `201 Created`：

```json
{
  "id": "doc-9a1393af3e004bf2",
  "caseId": "case-896406a64833445a",
  "filename": "案情材料.docx",
  "contentType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "size": 1071,
  "role": "input",
  "parseStatus": "queued",
  "parseTaskId": "4083e4bd-c1b0-422e-8b81-e392477f53fe",
  "createdAt": "2026-09-08T09:14:54.079611Z"
}
```

约定（已实现）：

- 上传成功表示文件已进 MinIO，材料记录与解析任务已在同一事务登记。
- **T2 和 T3 导入脚本拿到 `parseTaskId` 后只轮询，不再创建解析任务。**
- 同一用户、案件和 `Idempotency-Key` 的相同内容再次上传，返回原材料及原任务（实测仍 `201`，`id` / `parseTaskId` 不变）。
- 相同幂等键、不同内容 → `409 IDEMPOTENCY_CONFLICT`。
- `annotation` 会解析正文，但不得当作输入事实或已确认事实。

### 4. 材料列表与详情（刷新仍在）

```http
GET /v1/cases/case-896406a64833445a/documents?role=input&page=0&size=20
```

解析完成后实测 `200`：

```json
{
  "items": [
    {
      "id": "doc-9a1393af3e004bf2",
      "caseId": "case-896406a64833445a",
      "filename": "案情材料.docx",
      "contentType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "size": 1071,
      "role": "input",
      "parseStatus": "completed",
      "parseTaskId": "4083e4bd-c1b0-422e-8b81-e392477f53fe",
      "createdAt": "2026-09-08T09:14:54.079611Z"
    }
  ],
  "page": 0,
  "size": 20,
  "total": 1
}
```

```http
GET /v1/documents/doc-9a1393af3e004bf2
```

返回同一条材料。`parseStatus` 来自关联任务公开状态（`queued` / `running` / `completed` / `failed` / …）。正文从任务 `/result` 读，材料详情不存第二份。

同案 `annotation` 与 `input` 分开存储。同一次实测另传一份 annotation，得到不同 `id` / `parseTaskId`：

```json
{
  "id": "doc-a91bbb6d370a4553",
  "caseId": "case-f2124b9367104fad",
  "filename": ".t1-smoke-input.docx",
  "contentType": "application/octet-stream",
  "size": 1071,
  "role": "annotation",
  "parseStatus": "queued",
  "parseTaskId": "e330d5e8-4ace-491c-ba13-625e7b4e5ccc",
  "createdAt": "2026-09-08T09:12:29.523608Z"
}
```

`GET .../documents?role=annotation` 只返回 annotation；不带 `role` 时 input 与 annotation 同页出现。

### 5. 查询解析状态（只轮询，不新建）

不要用 `POST /v1/tasks` 建解析任务。内部入参形状如下，仅供核对（由上传接口写入）：

```json
{
  "query": "解析指定材料，提取正文、段落、表格和原文定位",
  "caseId": "case-896406a64833445a",
  "metadata": {
    "taskType": "document.parse",
    "documentId": "doc-9a1393af3e004bf2",
    "schemaVersion": "document.parse.v1"
  }
}
```

```http
GET /v1/tasks/4083e4bd-c1b0-422e-8b81-e392477f53fe
```

同会话另一次上传的轮询实测（阶段名已落地）：

queued / `accepted`：

```json
{
  "id": "1f5dba66-5899-4f61-92ea-b6fc83c51e9f",
  "requestId": "23801032-5377-4e7b-ad95-62075930b1ff",
  "executionId": "2517e53d-89d7-4e4c-9cb7-e044e174949e",
  "caseId": "case-f2124b9367104fad",
  "status": "queued",
  "currentStage": "accepted",
  "result": null,
  "errorCode": null,
  "error": null,
  "createdAt": "2026-09-08T09:12:24.950093Z",
  "updatedAt": "2026-09-08T09:12:24.950093Z"
}
```

running / `document_parsing`：

```json
{
  "id": "1f5dba66-5899-4f61-92ea-b6fc83c51e9f",
  "requestId": "23801032-5377-4e7b-ad95-62075930b1ff",
  "executionId": "2517e53d-89d7-4e4c-9cb7-e044e174949e",
  "caseId": "case-f2124b9367104fad",
  "status": "running",
  "currentStage": "document_parsing",
  "result": null,
  "errorCode": null,
  "error": null,
  "createdAt": "2026-09-08T09:12:24.950093Z",
  "updatedAt": "2026-09-08T09:12:25.839457Z"
}
```

completed / `output`（UTF-8 建案这一次）：

```json
{
  "id": "4083e4bd-c1b0-422e-8b81-e392477f53fe",
  "requestId": "b19a81ea-80ed-4861-9e27-61a385c99197",
  "executionId": "a09e5127-4658-48f7-972b-4c148ef5b6b9",
  "caseId": "case-896406a64833445a",
  "status": "completed",
  "currentStage": "output",
  "result": {
    "resultId": "9c2c76d1-61da-47aa-8654-dbdcd54b337c",
    "version": 1,
    "type": "workflow.output",
    "contentHash": "52e731d52bb149bbe12ccd45b7f6b0c8b8952753fd2c11d4fad63155302b0e93",
    "sourceRefs": []
  },
  "errorCode": null,
  "error": null,
  "createdAt": "2026-09-08T09:14:54.079611Z",
  "updatedAt": "2026-09-08T09:14:56.308047Z"
}
```

公开状态：`queued` / `running` / `completed` / `waiting_review` / `failed` / `timed_out` / `rejected`。T2 可每 2 秒轮询。没有百分比进度字段。

### 6. 读取解析结果

```http
GET /v1/tasks/4083e4bd-c1b0-422e-8b81-e392477f53fe/result
```

响应 `200`：

```json
{
  "resultId": "9c2c76d1-61da-47aa-8654-dbdcd54b337c",
  "version": 1,
  "type": "workflow.output",
  "contentHash": "52e731d52bb149bbe12ccd45b7f6b0c8b8952753fd2c11d4fad63155302b0e93",
  "content": {
    "text": "测试案例 001\n以下为开发样例正文。",
    "pages": [],
    "errors": [],
    "format": "docx",
    "tables": [
      {
        "rows": [
          ["项目", "内容"],
          ["材料类型", "开发样例"]
        ],
        "table": 1,
        "locator": "table:1"
      }
    ],
    "missing": [],
    "taskType": "document.parse",
    "warnings": [],
    "documentId": "doc-9a1393af3e004bf2",
    "paragraphs": [
      {
        "text": "测试案例 001",
        "style": "Normal",
        "locator": "paragraph:1",
        "paragraph": 1
      },
      {
        "text": "以下为开发样例正文。",
        "style": "Normal",
        "locator": "paragraph:2",
        "paragraph": 2
      }
    ],
    "schemaVersion": "document.parse.v1"
  }
}
```

外层仍是 `workflow.output`。用 `content.taskType=document.parse` 与 `content.schemaVersion=document.parse.v1` 区分解析业务。DOCX 无真实页码时 `pages` 为 `[]`，定位用 `paragraph:` / `table:`。

### 7. 失败、重试、越权、幂等

上传损坏 PDF 后任务进入 `failed`：

```json
{
  "id": "7e653112-1c84-4e56-a7a9-aa0ddf9c5c3e",
  "requestId": "3e4ce034-569c-42b9-a19a-e459b4bb8a62",
  "executionId": "39e20b4f-9a63-43d4-a83a-b21f451d30a7",
  "caseId": "case-f2124b9367104fad",
  "status": "failed",
  "currentStage": "document_parsing",
  "result": null,
  "errorCode": "DOCUMENT_PARSE_FAILED",
  "error": "无法解析该文件，请检查文件是否损坏或加密",
  "createdAt": "2026-09-08T09:12:29.959686Z",
  "updatedAt": "2026-09-08T09:12:32.597169Z"
}
```

```http
POST /v1/tasks/7e653112-1c84-4e56-a7a9-aa0ddf9c5c3e/retry
```

响应 `202`：同一 `id` 与 `requestId`，新 `executionId`，`currentStage=retry_requested`：

```json
{
  "id": "7e653112-1c84-4e56-a7a9-aa0ddf9c5c3e",
  "requestId": "3e4ce034-569c-42b9-a19a-e459b4bb8a62",
  "executionId": "229eb222-4338-451b-88bc-07746aaf2874",
  "caseId": "case-f2124b9367104fad",
  "status": "queued",
  "currentStage": "retry_requested",
  "result": null,
  "errorCode": null,
  "error": null,
  "createdAt": "2026-09-08T09:12:29.959686Z",
  "updatedAt": "2026-09-08T09:12:34.140984Z"
}
```

同步错误沿用 `ApiError`。实测：

未登录 `GET /v1/cases` → `401`：

```json
{
  "code": "UNAUTHORIZED",
  "message": "session required",
  "traceId": "68a1d97d-d948-428f-9c72-7b15d51239c6",
  "retryable": false
}
```

跨用户读他人案件 → `404 CASE_NOT_FOUND`（`案件不存在或不可访问`）。跨用户读材料 → `404 DOCUMENT_NOT_FOUND`。跨用户读任务 / 结果 → `404 CASE_NOT_FOUND`。

上传 `.txt` → `415`：

```json
{
  "code": "UNSUPPORTED_DOCUMENT_TYPE",
  "message": "仅支持 PDF 或 DOCX 材料",
  "traceId": "8359e433-ca46-4999-abd8-bfc0a7714322",
  "retryable": false
}
```

同 Key 不同内容 → `409`：

```json
{
  "code": "IDEMPOTENCY_CONFLICT",
  "message": "相同幂等键已用于不同内容的上传",
  "traceId": "9eda35b8-39e9-47d9-b923-c5e0ed4293b6",
  "retryable": false
}
```

| 场景 | HTTP / 任务状态 | 错误码 |
|---|---|---|
| 未登录 | 401 | UNAUTHORIZED |
| 案件不存在或无访问权限 | 404 | CASE_NOT_FOUND |
| 材料不存在或无访问权限 | 404 | DOCUMENT_NOT_FOUND |
| 上传不支持的格式 | 415 | UNSUPPORTED_DOCUMENT_TYPE |
| 同幂等键不同内容 | 409 | IDEMPOTENCY_CONFLICT |
| 解析文件损坏 | 任务 failed | DOCUMENT_PARSE_FAILED |
| 解析超时 | 任务 timed_out | DOCUMENT_PARSE_TIMEOUT |

## 三、给 T3：内部调用与返回

T3 复用现有 skill：

```python
skills.common.document.parse_docx.execute(payload)
skills.common.document.parse_pdf.execute(payload)
```

Engine 从 MinIO 回读字节后传入：

```json
{
  "document_id": "doc-9a1393af3e004bf2",
  "filename": "案情材料.docx",
  "content_base64": "<实际文件字节的 Base64>"
}
```

T2 不传存储密钥，也不直接调用 Engine。适配层把 skill 输出包成上面的 `document.parse.v1`（补 `locator`，致命 warnings 映射为任务 `failed`）。

公开 API 用 camelCase，内部 API 用 snake_case：

| Java 公开字段 | Engine 内部字段 |
|---|---|
| caseId | case_id |
| requestId | request_id |
| executionId | execution_id |
| currentStage | current_stage |
| errorCode | error_code |
| error | error_message |
| content，JSON 对象 | content_json，序列化 JSON 字符串 |

内部请求使用 `X-Service-Token`。Skill timeout 转为公开任务 `timed_out` / `DOCUMENT_PARSE_TIMEOUT`。

## 四、P0 验收（本次 Compose 实测）

- 登录后可创建、列表、读取案件。
- 上传 `input` 即返回 `parseTaskId`，`parseStatus=queued`；刷新后材料仍在。
- 轮询经过 `document_parsing` 到 `completed`；`/result` 的 `content.schemaVersion=document.parse.v1`。
- 损坏 PDF → `DOCUMENT_PARSE_FAILED`；`POST /retry` 保持同一 task id / requestId，换 executionId。
- 401 / 跨用户 404 / 415 / 同 Key 幂等 / 不同内容 409 均已打通。
- `input` 与 `annotation` 分条存储，各自有解析任务。

事实确认、量刑、法源检索不在本份 P0 交接里。
