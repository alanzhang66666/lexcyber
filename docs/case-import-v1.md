# LexCyber `case-import.v1` 包规范

`lexcyber.case-import.v1` 是协作方提交案件数据与材料的不可变交付格式。它只定义输入包、完整性和身份，不直接表示案件已获审核或已进入正式业务表。

## 载体与入口

包可以是一个目录或 ZIP，根目录必须包含 `case-import.json`。ZIP 校验不使用 `extractall()`；目录和 ZIP 采用相同的 POSIX 相对路径。禁止绝对路径、盘符、UNC、反斜杠、`.`/`..`、符号链接、特殊文件、加密 ZIP entry、重复路径和大小写冲突路径。

默认安全上限：manifest 1 MiB、单个 payload 10 MiB、单份材料 50 MiB、包内未压缩内容 512 MiB、最多 10,000 个 entry、ZIP 压缩比最多 100:1。

## 稳定身份

- `producer_id`：协作数据生产方，由平台分配并长期稳定。
- `package_id`：一条交付谱系的稳定 ID。
- `dataset_id`：业务数据集 ID。
- `revision`：该数据集的一次不可变发布。
- `external_case_id`：生产方范围内跨 revision 稳定的案件身份。
- `item_id`：当前包内唯一的处理单元 ID。

同一 `(producer_id, package_id, revision)` 必须始终对应同一个 `package_digest`。同 revision 不允许换包覆盖；新 revision 通过后续 Import API 生成差异并审核应用。

## Manifest

```json
{
  "schema_version": "lexcyber.case-import.v1",
  "package_id": "partner-a-cases",
  "producer_id": "partner-a",
  "dataset_id": "cases-2026",
  "revision": "2026-09-18.1",
  "created_at": "2026-09-18T08:00:00Z",
  "items": [
    {
      "item_id": "item-001",
      "external_case_id": "case-001",
      "resource_type": "case",
      "payload": {
        "path": "items/item-001/case.json",
        "media_type": "application/vnd.lexcyber.case-bundle+json;version=1",
        "schema_version": "lexcyber.case-bundle.v1",
        "size": 1234,
        "sha256": "<64 lowercase hex>"
      },
      "files": [
        {
          "file_id": "file-001",
          "document_id": "doc-001",
          "role": "case_material",
          "path": "items/item-001/files/material.docx",
          "media_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
          "size": 5678,
          "sha256": "<64 lowercase hex>"
        }
      ]
    }
  ],
  "package_digest": {
    "algorithm": "sha256",
    "canonicalization": "lexcyber.case-import.c14n.v1",
    "value": "<64 lowercase hex>"
  }
}
```

完整 JSON 约束见 `contracts/schemas/case-import-package-v1.schema.json`。`items` 支持 1 到 1,000 项；每项 payload 使用现有 `lexcyber.case-bundle.v1`。

## Digest 规范

计算 `package_digest.value` 时：

1. 深复制 manifest，将 `package_digest.value` 替换为 64 个字符 `0`。
2. 每项 `files` 按 `file_id` 升序排列，`items` 按 `item_id` 升序排列。
3. JSON 使用 UTF-8、对象键升序、无多余空白、保留非 ASCII 字符，禁止 NaN/Infinity。
4. 对结果计算 SHA-256 小写十六进制。

payload 和材料的 path、size、media type、SHA-256 均在 manifest 中，因此包摘要传递绑定全部声明内容；ZIP 时间戳、压缩方式和 entry 顺序不影响摘要。

Python 可调用：

```python
from engine.import_package import calculate_package_digest, load_import_package

package = load_import_package("partner-package.zip")
```

命令行校验：

```powershell
python scripts/validate_import_package.py "D:\incoming\partner-package.zip"
```

校验仅读取数据，不写 PostgreSQL、MinIO 或正式案件资源。

## 一致性门闩

- 所有声明路径必须存在，除 `case-import.json` 外不允许未声明文件。
- 实际 size 和 SHA-256 必须与 manifest 一致。
- PDF 必须有 `%PDF-` 文件头；DOCX 必须包含 `[Content_Types].xml` 与 `word/document.xml`。
- payload 必须通过 `collaboration-case-bundle.schema.json`。
- bundle `case_id` 必须等于 manifest `external_case_id`。
- manifest 文件集合必须与 bundle `documents` 一一对应，且 `document_id`、role、SHA-256 一致。
- evidence 只能引用 role 为 `case_material` 的材料。

本规范不包含法律确认。`candidate`、`conflicted`、待会签量刑规则和模板仍按现有人工复核边界处理。
