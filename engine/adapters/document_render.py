"""文书渲染执行体（P8）：draft.render → draft.v2。

approved template_package 的 body_template 用 {{ path }} 占位符；
path 在渲染视图上解析（与 evaluator 同一寻址语义）：

    {{facts.<key>.value}}          事实字段
    {{entities.<section>.count}}   实体计数
    {{amounts.<kind>.sum}}         金额聚合
    {{artifacts.<module>.<path>}}  上游模块工件 payload
    {{case_id}} / {{doc_type}}

占位符解析失败 → unresolved 收集，status=blocked 且不产正文
（服务端阻断，不是输出带【待补充】的半成品）。
"""
from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from engine.adapters.module_analysis import ModuleAnalysisError
from engine.rules import registry
from engine.rules.evaluator import _resolve, build_view

_PLACEHOLDER = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
_CHINESE_PLACEHOLDER = re.compile(r"【[^】]*】")


def render(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = payload.get("metadata") or {}
    doc_type = metadata.get("docType")
    if not doc_type:
        raise ModuleAnalysisError("DOC_TYPE_MISSING",
                                  "文书渲染缺少 metadata.docType")
    snapshot = metadata.get("factsSnapshot")
    if not isinstance(snapshot, dict):
        raise ModuleAnalysisError(
            "FACTS_SNAPSHOT_MISSING",
            "文书渲染缺少不可变事实快照（metadata.factsSnapshot）")
    try:
        as_of_date = registry.require_as_of_date(metadata)
    except registry.RegistryError as exc:
        raise ModuleAnalysisError(exc.code, str(exc)) from exc

    template = registry.active_template(str(doc_type))
    if template is None:
        raise ModuleAnalysisError(
            "TEMPLATE_UNAVAILABLE",
            f"doc_type {doc_type} 无已会签模板")

    artifacts = metadata.get("artifacts") or {}
    version_ids = metadata.get("artifactVersions") or {}
    if not isinstance(artifacts, dict) or not isinstance(version_ids, dict) or artifacts.keys() != version_ids.keys():
        raise ModuleAnalysisError("ARTIFACT_SNAPSHOT_MISSING", "上游内容必须绑定具体工件版本")
    try:
        frozen_artifacts = [{"module": name, "artifactVersionId": str(UUID(str(version_ids[name])))}
                            for name in sorted(artifacts)]
    except (ValueError, TypeError, AttributeError) as exc:
        raise ModuleAnalysisError("ARTIFACT_SNAPSHOT_INVALID", "上游工件版本必须为 UUID") from exc

    view = build_view(snapshot)
    view["case_id"] = payload.get("case_id")
    view["doc_type"] = doc_type
    view["artifacts"] = artifacts
    input_ref = payload.get("input_snapshot_ref") or ""
    facts_version_id = (input_ref[len("facts_version:"):]
                        if input_ref.startswith("facts_version:") else None)

    unresolved: list[dict[str, Any]] = []
    for name, artifact in artifacts.items():
        if not isinstance(artifact, dict) or artifact.get("status") == "blocked":
            unresolved.append({"path": f"artifacts.{name}", "reason": "upstream_blocked"})

    def substitute(match: re.Match) -> str:
        path = match.group(1).strip()
        found, value = _resolve(view, path)
        if not found or value is None:
            unresolved.append({"path": path, "reason": "unresolved_or_null"})
            return match.group(0)
        if isinstance(value, (dict, list)):
            import json
            return json.dumps(value, ensure_ascii=False)
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)

    body = _PLACEHOLDER.sub(substitute, template["bodyTemplate"])

    # Templates and substituted facts must never leak a human-facing
    # placeholder into a published artifact.  This catches both the normal
    # ``{{path}}`` form left unresolved and Chinese drafting markers such as
    # ``【待核实】`` (including markers introduced by a fact value).
    if _PLACEHOLDER.search(body) or _CHINESE_PLACEHOLDER.search(body):
        unresolved.append({"path": "body", "reason": "unresolved_placeholder"})

    # 模板声明的必填字段校验（field_schema.required[] 也是路径）
    field_schema = template.get("fieldSchema") or {}
    for req in field_schema.get("required") or []:
        found, value = _resolve(view, str(req))
        if not found or value is None:
            unresolved.append({"path": str(req), "reason": "required_field_missing"})

    status = "blocked" if unresolved else "rendered"
    body_out = {
        "schema_version": "draft.v2",
        "module": "draft",
        "status": status,
        "doc_type": doc_type,
        "case_id": payload.get("case_id"),
        "facts_version_id": facts_version_id,
        "input_snapshot_ref": input_ref or None,
        "template": {"templateId": template["templateId"],
                     "templateVersion": template["templateVersion"],
                     "contentHash": template["contentHash"]},
        "body": None if unresolved else body,
        "unresolved": unresolved,
        "dependency_snapshot": {
            "facts_version_id": facts_version_id,
            "as_of_date": as_of_date.isoformat(),
            "template": {"templateId": template["templateId"],
                         "templateVersion": template["templateVersion"],
                         "contentHash": template["contentHash"]},
            "artifacts": frozen_artifacts,
        },
        "human_review_required": True,
    }
    return {"final_output": body_out, "human_approval_required": True}


class DraftRenderRunner:
    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return render(payload)
