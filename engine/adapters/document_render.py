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
from engine.rules.inputs import InputValidator

_PLACEHOLDER = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
_CHINESE_PLACEHOLDER = re.compile(r"【[^】]*】")


def _valid_input_marker(marker: Any) -> bool:
    if not isinstance(marker, dict):
        return False
    if marker.get("schema_version") != "case.input-validation.v1":
        return False
    if marker.get("status") != "verified":
        return False
    checks = marker.get("checks")
    blockers = marker.get("blockers")
    if not isinstance(checks, list) or not isinstance(blockers, list) or blockers:
        return False
    return all(isinstance(check, dict) and check.get("status") == "verified"
               for check in checks)


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
    input_validator = InputValidator(snapshot, view)
    view["case_id"] = payload.get("case_id")
    view["doc_type"] = doc_type
    view["artifacts"] = artifacts
    input_ref = payload.get("input_snapshot_ref") or ""
    facts_version_id = (input_ref[len("facts_version:"):]
                        if input_ref.startswith("facts_version:") else None)

    unresolved: list[dict[str, Any]] = []
    for name, artifact in artifacts.items():
        artifact_path = f"artifacts.{name}"
        if not isinstance(artifact, dict) or artifact.get("status") == "blocked":
            unresolved.append({"path": artifact_path, "reason": "upstream_blocked"})
            input_validator._record(artifact_path, "document", "as_of", [], [], [
                {"code": "UPSTREAM_BLOCKED", "reason": "upstream artifact is blocked"}])
            continue
        marker = artifact.get("input_validation")
        marker_blocked = not _valid_input_marker(marker)
        input_validator._record(artifact_path, "document", "as_of",
                                [str(version_ids[name])], [],
                                [{"code": "UPSTREAM_INPUT_VALIDATION_BLOCKED",
                                  "reason": "upstream v2 input marker is missing or blocked"}]
                                if marker_blocked else [])
        if marker_blocked:
            unresolved.append({"path": f"artifacts.{name}.input_validation",
                               "reason": "upstream_input_validation_blocked"})

    def substitute(match: re.Match) -> str:
        path = match.group(1).strip()
        if not path.startswith("artifacts."):
            input_validator.check_path(path, phase="document", point="as_of")
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
        if not str(req).startswith("artifacts."):
            input_validator.check_path(str(req), phase="document", point="as_of")
        found, value = _resolve(view, str(req))
        if not found or value is None:
            unresolved.append({"path": str(req), "reason": "required_field_missing"})

    input_validation = input_validator.summary()
    if input_validation.get("blockers"):
        unresolved.extend({"path": item.get("path"), "reason": item.get("code", "input_blocked")}
                          for item in input_validation["blockers"])
    unresolved.extend(_document_constraints(template, view, metadata))
    section = _conditional_section(template, view)
    if section is _SECTION_MISSING:
        unresolved.append({"path": "conditional_sections", "reason": "conditional_section_missing"})
    elif isinstance(section, str):
        body = body.rstrip() + "\n" + section
        if _PLACEHOLDER.search(section) or _CHINESE_PLACEHOLDER.search(section):
            unresolved.append({"path": "conditional_sections", "reason": "unresolved_placeholder"})
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
        "input_validation": input_validation,
    }
    return {"final_output": body_out, "human_approval_required": True}


_SECTION_MISSING = object()


def _fact_value(view: dict[str, Any], key: str) -> Any:
    item = (view.get("facts") or {}).get(key)
    if not isinstance(item, dict) or item.get("value") is None:
        return None
    return item.get("value")


def _is_true(value: Any) -> bool:
    return value is True or (isinstance(value, str) and value.strip().lower() == "true")


def _is_false(value: Any) -> bool:
    return value is False or (isinstance(value, str) and value.strip().lower() == "false")


def _matches(actual: Any, expected: Any) -> bool:
    if isinstance(expected, bool):
        return _is_true(actual) if expected else _is_false(actual)
    return actual == expected


def _document_constraints(template: dict[str, Any], view: dict[str, Any],
                          metadata: dict[str, Any]) -> list[dict[str, str]]:
    schema = template.get("fieldSchema") or {}
    unresolved: list[dict[str, str]] = []
    applicability = schema.get("applicability")
    if isinstance(applicability, dict):
        selection = metadata.get("documentSelection")
        selection = selection if isinstance(selection, dict) else {}
        if applicability.get("manual_document_selection") and selection.get("confirmed") is not True:
            unresolved.append({"path": "documentSelection.confirmed", "reason": "manual_selection_required"})
        expected = applicability.get("document_disposition")
        if expected and selection.get("documentDisposition") != expected:
            unresolved.append({"path": "documentSelection.documentDisposition", "reason": "applicability_mismatch"})
        help_type = applicability.get("help_type")
        if help_type and _fact_value(view, "help_type") != help_type:
            unresolved.append({"path": "facts.help_type.value", "reason": "applicability_mismatch"})
        if selection.get("chargeBoundaryUnresolved") is True:
            unresolved.append({"path": "documentSelection.chargeBoundaryUnresolved", "reason": "boundary_unresolved"})
    exclusive = schema.get("mutually_exclusive")
    exclusive_field = schema.get("exclusive_field")
    if isinstance(exclusive, list) and exclusive and isinstance(exclusive_field, str):
        value = _fact_value(view, exclusive_field)
        path = f"facts.{exclusive_field}.value"
        if isinstance(value, list) or (isinstance(value, str) and "," in value):
            unresolved.append({"path": path, "reason": "mutually_exclusive"})
        elif value not in exclusive:
            unresolved.append({"path": path, "reason": "exclusive_value_invalid"})
    if _fact_value(view, "non_prosecution_type") == "conditional_minor":
        for key in schema.get("conditional_minor_required") or []:
            if not _is_true(_fact_value(view, str(key))):
                unresolved.append({"path": f"facts.{key}.value", "reason": "conditional_required_missing"})
        age = _fact_value(view, "offence_age")
        if isinstance(age, (int, float)) and not isinstance(age, bool) and age >= 18:
            unresolved.append({"path": "facts.offence_age.value", "reason": "conditional_minor_not_applicable"})
    for branch in schema.get("conditional_required") or []:
        if not isinstance(branch, dict):
            continue
        if not _matches(_fact_value(view, str(branch.get("fact"))), branch.get("eq")):
            continue
        for key in branch.get("required") or []:
            if _fact_value(view, str(key)) is None:
                unresolved.append({"path": f"facts.{key}.value", "reason": "conditional_required_missing"})
        for key in branch.get("must_omit") or []:
            if _fact_value(view, str(key)) is not None:
                unresolved.append({"path": f"facts.{key}.value", "reason": "mutually_exclusive"})
    return unresolved


def _conditional_section(template: dict[str, Any], view: dict[str, Any]) -> Any:
    schema = template.get("fieldSchema") or {}
    spec = schema.get("conditional_sections")
    if not isinstance(spec, dict):
        return None
    value = _fact_value(view, str(spec.get("fact") or ""))
    sections = spec.get("sections") if isinstance(spec.get("sections"), dict) else {}
    text = sections.get(value)
    if not isinstance(text, str) or not text.strip():
        return _SECTION_MISSING
    return text


class DraftRenderRunner:
    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return render(payload)
