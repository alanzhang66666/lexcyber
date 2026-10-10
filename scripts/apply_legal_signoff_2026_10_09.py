"""把 2026-10-09 法学生复核版会签清单落进系统（一次性、可重入）。

两个阶段：
  registry  在 engine 容器内运行（直接调 engine.rules.registry；唯一批准路径 signoff()）
            需 SIGNOFF_REVIEWER / SIGNOFF_ROLE；--dry-run 只打印动作。
            1) 10 条法源：按 legal_sources.json 同步别名 → 补掩隐新旧链 → signoff()
            2) 7 条规则 / 2 份模板：同内容新补丁版本入册 → signoff() → 旧版 superseded
  cases     在宿主机运行（公开 /v1 + /v2，LEXCYBER_USERNAME / LEXCYBER_PASSWORD）
            C 案注入键化覆盖层；B 案按黄某/陈某拆为两个演示案。

复核结论原文见 docs/legal-review/review-intake-2026-10-09.json；只映射复核人明确写出的判断。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
INTAKE = "docs/legal-review/review-intake-2026-10-09.json"
LOCATOR = "signoff:SIGNOFF-009@2026-10-09"
TAG = "法学生复核版会签清单 2026-10-09"

RULE_BUMPS = {
    "rule-conviction-assist-287-2-elements@1.0.0": "1.0.1",
    "rule-conviction-assist-severity-2019-threshold@1.0.1": "1.0.2",
    "rule-distinction-concealment-after-upstream@1.0.0": "1.0.1",
    "rule-distinction-fraud-accomplice-prior-collusion@1.0.0": "1.0.1",
    "rule-compliance-logs-retention-6m@1.0.0": "1.0.1",
    "rule-compliance-realname-verification@1.0.0": "1.0.1",
    "rule-sentencing-assist-base@1.0.1": "1.0.2",
}
TEMPLATE_BUMPS = {
    "indictment-draft@1.0.1": "1.0.2",
    "indictment-assist@1.0.0": "1.0.1",
}
SUPERSESSION = ("cn-concealment-interpretation-2015-2021", "cn-concealment-interpretation-2025-1-12")


def _load(path: str) -> dict[str, Any]:
    for base in (Path("/tmp/lexsignoff"), ROOT, Path.cwd()):
        candidate = base / path
        if candidate.is_file():
            return json.loads(candidate.read_text(encoding="utf-8"))
    raise SystemExit(f"missing {path}")


def _comment(signoff_id: str, conclusion: str, detail: str | None, extra: str | None = None) -> str:
    parts = [f"{signoff_id}｜{TAG}｜结论：{conclusion}"]
    if detail and detail.strip() and detail.strip() != "无":
        parts.append(("修改意见（待后续版本）：" if conclusion == "有条件同意" else "意见：") + detail.strip())
    if extra:
        parts.append(extra)
    return "｜".join(parts)


# ---------------------------------------------------------------------------
# registry 阶段（engine 容器内）
# ---------------------------------------------------------------------------

def run_registry(dry_run: bool) -> list[dict[str, Any]]:
    from engine.rules import registry
    from engine.store import connection

    reviewer = os.environ.get("SIGNOFF_REVIEWER", "").strip()
    role = os.environ.get("SIGNOFF_ROLE", "").strip()
    if not reviewer or not role:
        raise SystemExit("SIGNOFF_REVIEWER and SIGNOFF_ROLE are required")
    intake = _load(INTAKE)
    corpus = {s["id"]: s for s in _load("engine/adapters/legal_sources.json")["sources"]}
    records: list[dict[str, Any]] = []

    def act(message: str) -> None:
        print(("[dry-run] " if dry_run else "") + message, flush=True)

    def do_signoff(kind: str, key: str, comment: str) -> None:
        act(f"signoff {kind} {key} approved")
        if not dry_run:
            result = registry.signoff(kind, key, reviewer, role, "approved", comment)
            records.append({"signoffId": result["signoffId"], "subjectKind": kind, "subjectKey": key,
                            "reviewer": reviewer, "role": role, "decision": "approved", "comment": comment})

    # 1) 法源
    with connection() as conn:
        rows = {r[0]: r for r in conn.execute(
            "SELECT source_key, source_version, verification_level, source_id::text FROM engine.legal_source"
            " WHERE source_key = ANY(%s)", ([s["source_key"] for s in intake["legal_sources"]],)).fetchall()}
    missing = [s["source_key"] for s in intake["legal_sources"] if s["source_key"] not in rows]
    if missing:
        raise SystemExit(f"legal sources not registered: {missing}")
    for item in intake["legal_sources"]:
        key, version, level, source_id = rows[item["source_key"]]
        wanted = list(corpus[key].get("aliases") or [])
        with connection() as conn:
            current = [r[0] for r in conn.execute(
                "SELECT alias FROM engine.legal_source_alias WHERE source_id = %s", (source_id,)).fetchall()]
            add = [a for a in wanted if a not in current]
            remove = [a for a in current if a not in wanted]
            if (add or remove) and level != "pending":
                raise SystemExit(f"{key} already {level}; alias change must precede signoff")
            if add or remove:
                act(f"aliases {key}: +{add} -{remove}")
            if not dry_run:
                for alias in add:
                    conn.execute("INSERT INTO engine.legal_source_alias(source_id, alias) VALUES (%s,%s)",
                                 (source_id, alias))
                if remove:
                    conn.execute("DELETE FROM engine.legal_source_alias WHERE source_id = %s AND alias = ANY(%s)",
                                 (source_id, remove))
    pred, succ = rows[SUPERSESSION[0]][3], rows[SUPERSESSION[1]][3]
    with connection() as conn:
        linked = conn.execute(
            "SELECT 1 FROM engine.legal_source_supersession WHERE predecessor_id = %s AND successor_id = %s",
            (pred, succ)).fetchone()
    if not linked:
        act(f"supersession {SUPERSESSION[0]} -> {SUPERSESSION[1]} (replaces)")
        if not dry_run:
            registry.link_supersession(pred, succ, "replaces",
                                       "法释〔2025〕13号自2025-08-26起取代法释〔2015〕11号/〔2021〕8号（SIGNOFF-007 复核确认）")
    for item in intake["legal_sources"]:
        key, version, level, _ = rows[item["source_key"]]
        if level == "pending":
            do_signoff("legal_source", f"{key}@{version}",
                       _comment("SIGNOFF-007", item["conclusion"], item["comment"]))
        else:
            act(f"skip legal_source {key}@{version} ({level})")

    # 2) 规则
    rule_reviews = {r["subject"]: r for r in intake["rules"]}
    for old_key, new_version in RULE_BUMPS.items():
        rule_id, _, old_version = old_key.partition("@")
        new_key = f"{rule_id}@{new_version}"
        with connection() as conn:
            old = conn.execute(
                "SELECT family, legal_review_status, effective_from, effective_to, source_ids, predicate,"
                " outcome, required_evidence_kinds, coverage FROM engine.rule_package"
                " WHERE rule_id = %s AND rule_version = %s", (rule_id, old_version)).fetchone()
            new = conn.execute("SELECT legal_review_status FROM engine.rule_package"
                               " WHERE rule_id = %s AND rule_version = %s", (rule_id, new_version)).fetchone()
        if old is None:
            raise SystemExit(f"missing {old_key}")
        if new is None:
            act(f"register rule {new_key} (content copied from {old_key})")
            if not dry_run:
                registry.register_rule_package({
                    "rule_id": rule_id, "rule_version": new_version, "family": old[0],
                    "effective_from": old[2], "effective_to": old[3], "source_ids": old[4],
                    "predicate": old[5], "outcome": old[6], "required_evidence_kinds": old[7],
                    "coverage": old[8]})
            new = ("pending",)
        review = rule_reviews[old_key]
        signoff_id = "SIGNOFF-006/010" if rule_id == "rule-sentencing-assist-base" else "SIGNOFF-006"
        if new[0] == "pending":
            do_signoff("rule", new_key, _comment(signoff_id, review["conclusion"], review["comment"],
                                                 f"内容同 {old_key}，以正式会签替换占位会签"))
        if old[1] == "approved":
            act(f"supersede rule {old_key}")
            if not dry_run:
                with connection() as conn:
                    conn.execute("UPDATE engine.rule_package SET legal_review_status = 'superseded'"
                                 " WHERE rule_id = %s AND rule_version = %s AND legal_review_status = 'approved'",
                                 (rule_id, old_version))

    # 3) 模板
    template_reviews = {t["subject"]: t for t in intake["templates"]}
    mapping = template_reviews.get("案型→模板映射", {})
    for old_key, new_version in TEMPLATE_BUMPS.items():
        template_id, _, old_version = old_key.partition("@")
        new_key = f"{template_id}@{new_version}"
        with connection() as conn:
            old = conn.execute(
                "SELECT doc_type, legal_review_status, field_schema, body_template FROM engine.template_package"
                " WHERE template_id = %s AND template_version = %s", (template_id, old_version)).fetchone()
            new = conn.execute("SELECT legal_review_status FROM engine.template_package"
                               " WHERE template_id = %s AND template_version = %s",
                               (template_id, new_version)).fetchone()
        if old is None:
            raise SystemExit(f"missing {old_key}")
        if new is None:
            act(f"register template {new_key} (content copied from {old_key})")
            if not dry_run:
                registry.register_template({"template_id": template_id, "template_version": new_version,
                                            "doc_type": old[0], "field_schema": old[2], "body_template": old[3]})
            new = ("pending",)
        review = template_reviews[old_key]
        if new[0] == "pending":
            extra = f"案型→模板映射：{mapping.get('comment')}｜内容同 {old_key}，以正式会签替换占位会签"
            do_signoff("template", new_key, _comment("SIGNOFF-008/005", review["conclusion"], review["comment"], extra))
        if old[1] == "approved":
            act(f"supersede template {old_key}")
            if not dry_run:
                with connection() as conn:
                    conn.execute("UPDATE engine.template_package SET legal_review_status = 'superseded'"
                                 " WHERE template_id = %s AND template_version = %s"
                                 " AND legal_review_status = 'approved'", (template_id, old_version))
    print("SIGNOFF_RECORDS_JSON=" + json.dumps(records, ensure_ascii=False), flush=True)
    return records


# ---------------------------------------------------------------------------
# cases 阶段（公开 API）
# ---------------------------------------------------------------------------

def _request(base: str, method: str, path: str, token: str | None = None, body: Any = None) -> tuple[int, Any]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return exc.code, {"message": raw.decode("utf-8", "replace")}


def _ok(result: tuple[int, Any], expected: int, what: str) -> Any:
    status, body = result
    if status != expected:
        raise SystemExit(f"{what} failed: HTTP {status} {body}")
    return body


def _bundle(name: str) -> dict[str, Any]:
    return json.loads((ROOT / "demo_cases" / "three_case_demo" / name).read_text(encoding="utf-8"))


def _evidence(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"id": e["id"], "type": e["type"], "label": e["label"], "verificationStatus": "confirmed",
             "attributes": {"documentRef": e.get("document_id"), "bundleLocator": e.get("locator")}}
            for e in rows]


def _actors(rows: list[dict[str, Any]], roles: dict[str, str] | None = None) -> list[dict[str, Any]]:
    roles = roles or {}
    return [{"id": a["id"], "type": a["type"], "name": a["name"], "verificationStatus": "confirmed",
             "attributes": {"bundleRole": a.get("role"), **({"unitCrimeRole": roles[a["id"]]} if a["id"] in roles else {})}}
            for a in rows]


def _narrative(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"id": f["id"], "key": f["type"], "value": f["value"], "stage": f.get("stage"),
             "actorId": f.get("actor_id"), "evidenceIds": f.get("evidence_ids") or [],
             "locator": f"bundle:{f['id']}", "verificationStatus": f.get("verification_status", "confirmed")}
            for f in rows]


def _keyed(fact_id: str, key: str, value: str, actor: str | None, evidence: list[str]) -> dict[str, Any]:
    return {"id": fact_id, "key": key, "value": value, "actorId": actor, "evidenceIds": evidence,
            "locator": LOCATOR, "verificationStatus": "confirmed"}


def _amount(amount_id: str, label: str, value: int, evidence: list[str], component_of: str | None = None) -> dict[str, Any]:
    row = {"id": amount_id, "kind": "illegal_gain", "label": label, "value": value, "currency": "CNY",
           "evidenceIds": evidence, "verificationStatus": "confirmed", "attributes": {"locator": LOCATOR}}
    if component_of:
        row["componentOf"] = component_of
    return row


def overlay_c() -> dict[str, list[dict[str, Any]]]:
    b = _bundle("case-c-unit-crossborder.json")
    company = "actor-c-company"
    facts = _narrative(b["facts"]) + [
        _keyed("ovl-c-contact-timing", "contact_timing", "before_upstream", company, ["ev-c-02", "ev-c-05"]),
        _keyed("ovl-c-prior-collusion", "prior_collusion", "false", company, ["ev-c-12"]),
        _keyed("ovl-c-upstream-completed", "upstream_crime_completed", "true", "actor-c-client", ["ev-c-06"]),
        _keyed("ovl-c-unit-crime", "unit_crime_subject", "true", company, ["ev-c-04", "ev-c-08"]),
        _keyed("ovl-c-cross-border", "cross_border_connection", "true", company, ["ev-c-02", "ev-c-05"]),
    ]
    jurisdiction = [{"id": j["id"], "type": j["type"], "value": j["value"], "evidenceIds": j.get("evidence_ids") or [],
                     "verificationStatus": j.get("verification_status", "confirmed")} for j in b["jurisdiction_connections"]]
    jurisdiction += [
        {"id": "ovl-c-jur-foreign-client", "type": "cross_border_connection", "value": "境外客户",
         "evidenceIds": ["ev-c-02"], "verificationStatus": "confirmed"},
        {"id": "ovl-c-jur-foreign-server", "type": "cross_border_connection", "value": "客户要求使用境外服务器",
         "evidenceIds": ["ev-c-02"], "verificationStatus": "confirmed"},
        {"id": "ovl-c-jur-data-transfer", "type": "cross_border_connection", "value": "用户数据向境外服务器实时传输",
         "evidenceIds": ["ev-c-05"], "verificationStatus": "confirmed"},
    ]
    return {
        "evidence": _evidence(b["evidence"]),
        "actors": _actors(b["actors"], {company: "unit_crime_subject",
                                        "actor-c-jia": "directly_responsible_manager",
                                        "actor-c-yi": "other_directly_responsible_person"}),
        "facts": facts,
        "amounts": [
            _amount("ovl-c-amount-service-fee", "A公司涉案项目技术服务收入（单位违法所得）", 118000, ["ev-c-07"]),
            _amount("ovl-c-amount-company-receipt", "进入公司账户部分（11.8万元组成部分，不另行累计）", 98000,
                    ["ev-c-07"], "ovl-c-amount-service-fee"),
            _amount("ovl-c-amount-project-bonus", "支付给技术人员的项目奖金（11.8万元组成部分，不另行累计）", 20000,
                    ["ev-c-07"], "ovl-c-amount-service-fee"),
        ],
        "jurisdiction-connections": jurisdiction,
    }


def overlay_b(person: str) -> dict[str, list[dict[str, Any]]]:
    b = _bundle("case-b-proceeds.json")
    is_chen = person == "chen"
    actor_ids = {"actor-b-chen", "actor-b-042-upstream"} if is_chen else {"actor-b-company", "actor-b-huang", "actor-b-upstream"}
    evidence = [e for e in b["evidence"] if e["id"].startswith("ev-b-042-") == is_chen]
    facts = _narrative([f for f in b["facts"] if f.get("actor_id") in actor_ids])
    if is_chen:
        actor = "actor-b-chen"
        facts += [
            _keyed("ovl-b-chen-contact-timing", "contact_timing", "after_upstream", actor, ["ev-b-042-04"]),
            _keyed("ovl-b-chen-prior-collusion", "prior_collusion", "false", actor, ["ev-b-042-01", "ev-b-042-02"]),
            _keyed("ovl-b-chen-upstream-completed", "upstream_crime_completed", "true", "actor-b-042-upstream", ["ev-b-042-04"]),
            _keyed("ovl-b-chen-cross-border", "cross_border_connection", "true", "actor-b-042-upstream", ["ev-b-042-03"]),
        ]
        amounts = [_amount("ovl-b-chen-illegal-gain", "陈某个人违法所得", 6409, ["ev-b-042-02"])]
        jurisdiction = [{"id": "ovl-b-chen-jur-cross-border", "type": "cross_border_connection",
                         "value": "境外诈骗团伙成员遥控、使用境外加密通讯软件、资金经跨境支付通道归集境外，部分取现发生于边境城市",
                         "evidenceIds": ["ev-b-042-03"], "verificationStatus": "confirmed"}]
    else:
        actor = "actor-b-huang"
        facts += [
            _keyed("ovl-b-huang-contact-timing", "contact_timing", "during_upstream", actor, ["ev-b-03"]),
            _keyed("ovl-b-huang-prior-collusion", "prior_collusion", "false", actor, ["ev-b-09"]),
            _keyed("ovl-b-huang-upstream-completed", "upstream_crime_completed", "false", "actor-b-upstream", ["ev-b-03"]),
            _keyed("ovl-b-huang-unit-crime", "unit_crime_subject", "false", "actor-b-company", ["ev-b-07", "ev-b-10"]),
        ]
        amounts = [_amount("ovl-b-huang-illegal-gain", "黄某个人违法所得", 4200, ["ev-b-06"])]
        jurisdiction = []
    return {"evidence": _evidence(evidence), "actors": _actors([a for a in b["actors"] if a["id"] in actor_ids]),
            "facts": facts, "amounts": amounts, "jurisdiction-connections": jurisdiction}


def _has_overlay(base: str, token: str, case_id: str) -> bool:
    head = _ok(_request(base, "GET", f"/v2/cases/{case_id}/facts-head", token), 200, "facts head")
    version_id = head.get("confirmedFactsVersionId")
    if not version_id:
        return False
    detail = _ok(_request(base, "GET", f"/v2/cases/{case_id}/facts-versions/{version_id}", token), 200, "facts version")
    return any(item.get("locator") == LOCATOR for item in (detail.get("payload") or {}).get("items") or [])


def _write_and_confirm(base: str, token: str, case_id: str, entities: dict[str, list[dict[str, Any]]], dry_run: bool) -> str | None:
    if _has_overlay(base, token, case_id):
        print(f"skip case {case_id}: overlay already confirmed", flush=True)
        return None
    print(("[dry-run] " if dry_run else "") + f"write overlay to {case_id}: "
          + ", ".join(f"{k}={len(v)}" for k, v in entities.items()), flush=True)
    if dry_run:
        return None
    for kind in ("evidence", "actors", "facts", "amounts", "jurisdiction-connections"):
        _ok(_request(base, "PUT", f"/v2/cases/{case_id}/facts-entities/{kind}", token, {"items": entities[kind]}),
            200, f"PUT {kind} {case_id}")
    head = _ok(_request(base, "GET", f"/v2/cases/{case_id}/facts-head", token), 200, "facts head")
    version = _ok(_request(base, "POST", f"/v2/cases/{case_id}/facts-versions", token), 201, "create facts version")
    version_id = version.get("factsVersionId")
    _ok(_request(base, "POST", f"/v2/cases/{case_id}/facts-versions/{version_id}/confirm", token,
                 {"expectedConfirmedFactsVersionId": head.get("confirmedFactsVersionId")}), 200, "confirm")
    print(f"confirmed {case_id} facts_version={version_id}", flush=True)
    return version_id


def run_cases(base: str, c_case_id: str, dry_run: bool) -> None:
    username, password = os.environ.get("LEXCYBER_USERNAME", ""), os.environ.get("LEXCYBER_PASSWORD", "")
    if not username or not password:
        raise SystemExit("LEXCYBER_USERNAME and LEXCYBER_PASSWORD are required")
    token = _ok(_request(base, "POST", "/v1/auth/login", body={"username": username, "password": password}),
                200, "login")["token"]
    _write_and_confirm(base, token, c_case_id, overlay_c(), dry_run)

    cases: list[dict[str, Any]] = []
    page = 0
    while True:
        body = _ok(_request(base, "GET", f"/v1/cases?page={page}&size=100", token), 200, "list cases")
        cases += body.get("items") or []
        if len(cases) >= body.get("total", 0) or not body.get("items"):
            break
        page += 1
    for person, name in (("huang", "黄某"), ("chen", "陈某")):
        external = f"demo-case-b-proceeds#{person}"
        existing = [c for c in cases if (c.get("metadata") or {}).get("externalCaseId") == external]
        if len(existing) > 1:
            raise SystemExit(f"ambiguous cases for {external}")
        if existing:
            case_id = existing[0]["id"]
        elif dry_run:
            print(f"[dry-run] create case {external}", flush=True)
            case_id = None
        else:
            created = _ok(_request(base, "POST", "/v1/cases", token, {
                "title": f"案例B拆分｜{name}（{'案例042资金处置' if person == 'chen' else '案例009帮助行为'}）",
                "jurisdiction": "CN", "asOfDate": "2026-09-18",
                "metadata": {"datasetCaseId": "B", "externalCaseId": external,
                             "derivedFrom": "demo-case-b-proceeds", "splitActor": f"actor-b-{person}",
                             "legalReview": "SIGNOFF-009@2026-10-09"}}), 201, f"create {external}")
            case_id = created["id"]
            print(f"created case {external} = {case_id}", flush=True)
        if case_id:
            _write_and_confirm(base, token, case_id, overlay_b(person), dry_run)
        else:
            print(f"[dry-run] overlay {external}: " + ", ".join(f"{k}={len(v)}" for k, v in overlay_b(person).items()))


# ---------------------------------------------------------------------------
# workbook 阶段：把 signoff 记录回填到清单副本的「正式会签记录」页
# ---------------------------------------------------------------------------

def run_workbook(workbook: str, records_path: str, out: str) -> None:
    import shutil
    import tempfile
    import xml.etree.ElementTree as ET

    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    ET.register_namespace("", ns)
    records = json.loads(Path(records_path).read_text(encoding="utf-8"))
    records = [r for r in records if r.get("signoffId")]
    if not records:
        raise SystemExit("records file has no signoff rows")
    tmp = Path(tempfile.mkdtemp(prefix="lexsignoff-wb-"))
    try:
        import zipfile
        with zipfile.ZipFile(workbook) as z:
            z.extractall(tmp)
        sheet_path = tmp / "xl" / "worksheets" / "sheet9.xml"
        tree = ET.parse(sheet_path)
        root = tree.getroot()
        data = root.find(f"{{{ns}}}sheetData")
        rows = list(data.findall(f"{{{ns}}}row"))
        keep: list[Any] = []  # 保留原有的非空说明行，挪到记录之后
        for row in rows[1:]:
            text = "".join(t.text or "" for t in row.iter(f"{{{ns}}}t")).strip()
            if text:
                keep.append(row)
            data.remove(row)
        row_no = 1
        for rec in records:
            row_no += 1
            row = ET.SubElement(data, f"{{{ns}}}row", {"r": str(row_no)})
            values = [rec["signoffId"], rec["subjectKind"], rec["subjectKey"], rec["reviewer"],
                      rec["role"], rec["decision"], "2026-10-09", rec["comment"]]
            for col, value in zip("ABCDEFGH", values):
                cell = ET.SubElement(row, f"{{{ns}}}c", {"r": f"{col}{row_no}", "t": "inlineStr"})
                ET.SubElement(ET.SubElement(cell, f"{{{ns}}}is"), f"{{{ns}}}t").text = value
        for note in keep:
            row_no += 1
            note.set("r", str(row_no))
            for cell in note.findall(f"{{{ns}}}c"):
                ref = cell.get("r")
                if ref:
                    cell.set("r", ref[0] + str(row_no))
            data.append(note)
        # 原表说明行（shared string）在重建时被移除，作为已归档注释补回
        row_no += 1
        note_row = ET.SubElement(data, f"{{{ns}}}row", {"r": str(row_no)})
        note_cell = ET.SubElement(note_row, f"{{{ns}}}c", {"r": f"A{row_no}", "t": "inlineStr"})
        ET.SubElement(ET.SubElement(note_cell, f"{{{ns}}}is"), f"{{{ns}}}t").text = (
            "原表说明：填写完成后由工程侧逐条执行 registry.signoff()——已由 "
            "scripts/apply_legal_signoff_2026_10_09.py 执行，以上 19 条为系统生成的正式会签记录。")
        tree.write(sheet_path, encoding="UTF-8", xml_declaration=True)
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for file in sorted(tmp.rglob("*")):
                if file.is_file():
                    z.write(file, file.relative_to(tmp).as_posix())
        print(f"wrote {out} ({len(records)} records)", flush=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("phase", choices=("registry", "cases", "workbook"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--base-url", default=os.environ.get("LEXCYBER_BASE_URL", "http://127.0.0.1:18080"))
    parser.add_argument("--c-case-id", default="ff917bbd-6b90-4c7e-98cb-e8ade99fe89f")
    parser.add_argument("--workbook", default=r"D:\法学会签清单-法学生复核版-2026-10-09.xlsx")
    parser.add_argument("--records", default="docs/legal-review/signoff-records-2026-10-09.json")
    parser.add_argument("--out", default="docs/legal-review/法学会签清单-法学生复核版-2026-10-09-已入册.xlsx")
    args = parser.parse_args()
    if args.phase == "registry":
        run_registry(args.dry_run)
    elif args.phase == "cases":
        run_cases(args.base_url, args.c_case_id, args.dry_run)
    else:
        run_workbook(args.workbook, args.records, args.out)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
