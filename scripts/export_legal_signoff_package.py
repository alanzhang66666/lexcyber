"""导出法学会签材料包：Word 会签文档 + Excel 跟踪工作簿。

数据源为仓库内语料与清单（docs/legal-signoff-checklist.md、
engine/rules/corpus/、engine/adapters/legal_sources.json、
demo_cases/three_case_demo/、docs/adr/ADR-0003），生成物落在
docs/legal-review/，供法学负责人离线审阅与回填。
"""
from __future__ import annotations

import json
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "legal-review"
DATE = "2026-09-26"

DISCLAIMER = (
    "本平台为辅助研判工具，不替代司法裁量，不产出量刑、责任或犯罪终局结论；"
    "所有模块结果均标记 human_review_required，须经具备资质人员复核后方可使用。"
)


def load_json(rel: str):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


RULES = [r for r in load_json("engine/rules/corpus/core_rules.json")["rules"]]
TEMPLATES = load_json("engine/rules/corpus/core_templates.json")["templates"]
SOURCES = load_json("engine/adapters/legal_sources.json")["sources"]

# 规则可读摘要（谓词 → 中文评审语言），阈值/取值必须与语料一致。
RULE_NOTES = {
    "rule-conviction-assist-287-2-elements": {
        "name": "帮信罪构成要件（刑法第287条之二）",
        "predicate": "全部满足：① knowledge_of_crime ∈ {explicit 明知, presumed 应知}；② help_type ∈ {互联网接入、服务器托管、网络存储、通讯传输、支付结算、广告推广、技术支持} 七类帮助之一；③ upstream_crime_established = true（上游犯罪成立）。",
        "review": "确认「明知」二分取值与帮助行为七类枚举的映射口径；确认三要件全部命中仅输出 charge_candidate（候选罪名提示），不构成定罪结论。",
    },
    "rule-conviction-assist-severity-2019-threshold": {
        "name": "帮信罪「情节严重」门槛（2019解释/2025意见）",
        "predicate": "任一满足：① payment_settlement_amount ≥ 200,000 元（2019解释20万支付结算线）；② assisted_targets ≥ 3 且 payment_settlement_amount ≥ 300,000 元（2025意见三账户30万流入线）；③ illegal_gain ≥ 10,000 元（违法所得线）。",
        "review": "确认两条支付结算路径为择一不叠加；确认金额口径统一 payment_settlement_amount（ADR-0003 封闭集）；确认 1.0.0 → 1.0.1 版本化修正后旧版已 superseded。",
    },
    "rule-distinction-concealment-after-upstream": {
        "name": "掩隐与帮信界分——既遂后介入",
        "predicate": "全部满足：upstream_crime_completed = true 且 contact_timing = after_upstream。",
        "review": "确认「上游既遂后介入转移赃款 → 掩隐方向」的提示措辞；确认该结果仍需排除事前通谋，不直接定掩隐。",
    },
    "rule-distinction-fraud-accomplice-prior-collusion": {
        "name": "诈骗共犯风险提示——事前通谋",
        "predicate": "全部满足：prior_collusion = true 且 contact_timing = before_upstream。",
        "review": "确认「事前通谋 + 提供支持 → 诈骗共犯评价风险」仅作风险提示，分工深度由人工研判。",
    },
    "rule-compliance-logs-retention-6m": {
        "name": "合规义务——网络日志留存",
        "predicate": "log_retention_months ≥ 6。",
        "review": "确认「日志留存不少于六个月」义务口径与 finding/severity=info 的提示级别。",
    },
    "rule-compliance-realname-verification": {
        "name": "合规义务——真实身份核验",
        "predicate": "has_realname_verification = true。",
        "review": "确认「用户真实身份信息核验」义务口径。",
    },
    "rule-sentencing-assist-base": {
        "name": "帮信罪基准刑与情节调节",
        "predicate": "前置 upstream_crime_established = true；基准档：payment_settlement ≥30万→18月 / ≥20万→12月 / illegal_gain ≥1万→9月；调节：自首-30%、坦白-10%、认罪认罚-20%（percent_of_base）；上限36月；罚金并处或单处由裁量。",
        "review": "重点：基准档取值与案载裁量的对应关系须逐档会签（见「案例A量刑偏差」）；确认调节项幅度、叠加顺序与上限夹逼口径。",
    },
}

SIGNOFF_ROWS = [
    ("SIGNOFF-001", "检索公开口：法源检索结果、来源、时间与引用范围可用于辅助研判", "法学负责人、检索轨道负责人", "待签", "501", "R3"),
    ("SIGNOFF-002", "量刑公开口：事实输入、规则依据、计算结果与展示边界", "法学负责人、量刑轨道负责人", "待签", "501", "R3"),
    ("SIGNOFF-003", "compliance.analyze 案件级合规分析边界", "法学负责人、合规轨道负责人", "待签", "501", "R3"),
    ("SIGNOFF-004", "conviction.analyze 案件级定罪分析边界", "法学负责人、定罪轨道负责人", "待签", "501", "R3"),
    ("SIGNOFF-005", "文书字段字典：draftType/templateVersion 语义与可编辑边界", "法学负责人、文书产品负责人", "待签", "501", "R4"),
    ("SIGNOFF-006", "core_rules.json 七条规则底稿的谓词化表达（阈值、枚举、法源绑定）", "法学负责人、定罪轨道负责人", "待签（e2e-reviewer 占位）", "能力门闩", "—"),
    ("SIGNOFF-007", "legal_sources.json 十条法源及新旧链/supersession 语义", "法学负责人", "待签（占位）", "能力门闩", "—"),
    ("SIGNOFF-008", "core_templates.json 两份模板 + draftType/占位符字段字典 + 案型→doc_type 映射", "法学负责人、文书产品负责人", "待签（占位）", "能力门闩", "—"),
    ("SIGNOFF-009", "演示案 B/C 结构化事实覆盖层映射（叙述事实→求值器键 + 金额封闭集归类）", "法学负责人、产品经理", "待签（未开始）", "—", "—"),
    ("SIGNOFF-010", "案例A量刑基准档偏差校正：规则 9.0→8.1 月 vs 案载审定基准 12–18 月", "法学负责人、量刑轨道负责人", "待签", "—", "—"),
]

FACT_KEYS = [
    ("knowledge_of_crime", "明知状态", "{explicit 明知, presumed 应知}", "帮信要件①"),
    ("help_type", "帮助类型", "七类枚举：internet_access/server_hosting/network_storage/communication_transmission/payment_settlement/advertising_promotion/technical_support", "帮信要件②"),
    ("upstream_crime_established", "上游犯罪成立", "bool", "帮信要件③ + 量刑前置"),
    ("upstream_crime_completed", "上游犯罪既遂", "bool", "掩隐界分"),
    ("contact_timing", "介入时点", "{before_upstream, after_upstream}", "界分双规则"),
    ("prior_collusion", "事前通谋", "bool", "诈骗共犯提示"),
    ("assisted_targets", "帮助对象数量", "int", "2025意见三账户路径"),
    ("log_retention_months", "日志留存月数", "num", "合规义务"),
    ("has_realname_verification", "实名核验", "bool", "合规义务"),
    ("has_surrender / has_confession / has_guilty_plea", "自首/坦白/认罪认罚", "bool", "量刑调节项"),
    ("defendant_name", "被告人名称", "text", "文书必填字段"),
]

AMOUNT_KINDS = [
    ("payment_settlement_amount", "支付结算金额（帮信「情节严重」要件）"),
    ("illegal_gain", "违法所得"),
    ("crime_amount", "上游犯罪金额 / 被害人损失"),
    ("business_revenue", "经营性收入，不入罪量评价"),
    ("recovery", "追缴数额"),
    ("fine", "罚金"),
]

CASE_ROWS = [
    ("demo-case-a-helping", "科技公司员工违规销售GOIP设备帮助行为案",
     "已完成（示例）", "已按 bundle 审定结论注入键化事实（locator: bundle:* 可溯源）：28万→business_revenue（原审定「非支付结算」）、3万→illegal_gain、96万→crime_amount；不写 payment_settlement_amount。"),
    ("demo-case-b-proceeds", "案例009帮助行为与案例042资金处置界分对照案",
     "待法学审定", "须由法学审定：帮助/处置两段行为的事实键映射（contact_timing/prior_collusion/upstream_crime_completed）、金额归类（含 non_crime_flow、personal_profit 等待归类口径）。"),
    ("demo-case-c-unit-crossborder", "网络科技公司及管理人员跨境技术帮助案",
     "待法学审定", "须由法学审定：单位犯罪与自然人责任的事实键拆分、跨境要素的 jurisdiction_connection 表达、金额归类。"),
]


def build_word() -> Path:
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Microsoft YaHei"
    style.font.size = Pt(10.5)

    title = doc.add_heading("LexCyber 法学会签材料包", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub = doc.add_paragraph(f"生成日期：{DATE}　|　版本：v1.3 生命周期架构　|　密级：内部评审材料")
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER

    p = doc.add_paragraph()
    run = p.add_run("免责声明：" + DISCLAIMER)
    run.bold = True
    run.font.color.rgb = RGBColor(0x99, 0x33, 0x00)

    doc.add_heading("一、背景与现状", level=1)
    doc.add_paragraph(
        "平台五段管道（合规筛查 → 定罪研判 → 量刑分析 → 文书生成 → 人工复核与归档）"
        "已在 compose 全栈端到端实测。规则、法源、模板统一由注册表管理，"
        "仅 approved 条目可被执行体消费；所有评审结论须通过 signoff() 落审计记录，"
        "直连 SQL 改写状态会被触发器拒绝。"
    )
    doc.add_paragraph(
        "当前开发库中全部 approved 条目的会签人为占位标识 e2e-reviewer，"
        "不构成正式法学批准。本材料包列出的全部事项均须法学负责人重走 signoff() "
        "后方可视为正式启用。"
    )

    doc.add_heading("二、会签事项总览", level=1)
    table = doc.add_table(rows=1, cols=5)
    table.style = "Light Grid Accent 1"
    hdr = table.rows[0].cells
    for i, h in enumerate(["条目标识", "待会签内容", "负责人", "状态", "返回码/门闩"]):
        hdr[i].text = h
    for row in SIGNOFF_ROWS:
        cells = table.add_row().cells
        for i, v in enumerate(row[:5]):
            cells[i].text = str(v)

    doc.add_heading("三、规则语料复核（SIGNOFF-006，共 7 条）", level=1)
    doc.add_paragraph(
        "语料文件：engine/rules/corpus/core_rules.json。"
        "每条规则含谓词（predicate，求值器 DSL）与产出（outcome）。"
        "以下将谓词转写为评审语言，请以语料原文为准逐项核对。"
    )
    for r in RULES:
        rid = f"{r['rule_id']}@{r['rule_version']}"
        note = RULE_NOTES.get(r["rule_id"], {})
        doc.add_heading(f"{note.get('name', '')}（{rid}，族：{r['family']}）", level=2)
        doc.add_paragraph(f"谓词转写：{note.get('predicate', json.dumps(r.get('predicate'), ensure_ascii=False))}")
        doc.add_paragraph(f"产出语义：{json.dumps(r.get('outcome'), ensure_ascii=False)[:400]}")
        doc.add_paragraph(f"复核要点：{note.get('review', '—')}")

    doc.add_heading("四、法源清单复核（SIGNOFF-007，共 10 条）", level=1)
    doc.add_paragraph(
        "语料文件：engine/adapters/legal_sources.json。"
        "法源支持别名与新旧链（supersession）；分析结果为每条命中规则做双时点法源解析。"
        "请核对各法源效力期间、别名覆盖与新旧链声明。"
    )
    t = doc.add_table(rows=1, cols=4)
    t.style = "Light Grid Accent 1"
    for i, h in enumerate(t.rows[0].cells):
        h.text = ["法源标识", "名称/文号", "效力期间", "别名"][i]
    for s in SOURCES:
        c = t.add_row().cells
        c[0].text = s["id"]
        c[1].text = f"{s['title']}｜{s.get('document_number','')}"
        c[2].text = f"{s.get('effective_from','?')} → {s.get('effective_to') or '现行'}"
        c[3].text = "、".join(s.get("aliases", []))

    doc.add_heading("五、模板语料复核（SIGNOFF-008）", level=1)
    doc.add_paragraph(
        "策略：按案型分模板。doc_type 决定 active_template；必填字段解析失败 → "
        "blocked 不产正文（fail-closed）。当前在册："
    )
    for tp in [
        ("indictment-draft@1.0.1", "indictment", "支付结算型", "含 amounts.payment_settlement_amount 等占位符", "approved（占位会签）"),
        ("indictment-assist@1.0.0", "indictment-assist", "帮信通用型（非支付结算）", "必填：facts.defendant_name.value", "approved（占位会签，新入册）"),
    ]:
        doc.add_paragraph(f"• {tp[0]}（doc_type={tp[1]}，{tp[2]}）：{tp[3]}；状态 {tp[4]}", style="List Bullet")
    doc.add_paragraph(
        "请复核：①字段字典（占位符路径 ↔ 法律语义）；②必填口径；③案型 → doc_type 映射"
        "（何种案件应走 indictment 而非 indictment-assist，及后续是否增设其他案型模板）。"
    )

    doc.add_heading("六、演示案结构化覆盖层（SIGNOFF-009）", level=1)
    doc.add_paragraph(
        "演示案原始事实为叙述文本，与求值器键模型存在代差；金额口径（如 non_crime_flow、"
        "personal_profit）不在 ADR-0003 封闭集。覆盖层映射属法律定性判断，"
        "须法学审定后注入，工程侧不自行定性。案例 A 已完成示例（locator: bundle:* 可溯源）。"
    )
    t = doc.add_table(rows=1, cols=4)
    t.style = "Light Grid Accent 1"
    for i, h in enumerate(t.rows[0].cells):
        h.text = ["案件", "标题", "状态", "待审定映射"][i]
    for row in CASE_ROWS:
        c = t.add_row().cells
        for i, v in enumerate(row):
            c[i].text = v
    doc.add_paragraph("")
    doc.add_paragraph("求值器事实键字典（覆盖层目标模型）：")
    t = doc.add_table(rows=1, cols=4)
    t.style = "Light Grid Accent 1"
    for i, h in enumerate(t.rows[0].cells):
        h.text = ["键", "含义", "取值", "用于"][i]
    for row in FACT_KEYS:
        c = t.add_row().cells
        for i, v in enumerate(row):
            c[i].text = v
    doc.add_paragraph("金额 kind 封闭集（ADR-0003，新增须法学会签 + ADR + 前向迁移）：")
    for k, v in AMOUNT_KINDS:
        doc.add_paragraph(f"• {k} — {v}", style="List Bullet")

    doc.add_heading("七、案例A量刑偏差（SIGNOFF-010）", level=1)
    doc.add_paragraph(
        "规则计算：基准档 illegal_gain≥1万 → 9.0 月，坦白 -10% → 8.1 月。"
        "案载（bundle）审定基准：12–18 月。请确认偏差归因——"
        "是规则语料基准档取值偏低（须校语料或另立版本），还是案载裁量包含未建模情节。"
        "修正方式：规则以新版本入册（approved 不可改），旧版 superseded。"
    )

    doc.add_heading("八、会签执行方式", level=1)
    doc.add_paragraph(
        "会签通过注册表 signoff() 完成（engine.rules.registry.signoff），"
        "字段：subject_kind（rule/template/legal_source）、subject_key（id@version）、"
        "reviewer、role、decision（approved/rejected）、comment。"
        "签后条目状态翻转并落 signoff_record 审计行；占位会签以正式会签记录覆盖，"
        "历史记录保留。不得直接 SQL 修改 legal_review_status（触发器拒绝）。"
    )
    doc.add_heading("签署", level=1)
    doc.add_paragraph("法学负责人：＿＿＿＿＿＿＿＿　　日期：＿＿＿＿＿＿")
    doc.add_paragraph("工程负责人：＿＿＿＿＿＿＿＿　　产品负责人：＿＿＿＿＿＿")

    path = OUT / f"法学会签材料包-{DATE}.docx"
    doc.save(path)
    return path


HDR_FILL = PatternFill("solid", fgColor="2B579A")
HDR_FONT = Font(color="FFFFFF", bold=True, size=10)
BODY = Alignment(vertical="top", wrap_text=True)


def sheet(ws, headers, rows, widths):
    for i, h in enumerate(headers, 1):
        c = ws.cell(1, i, h)
        c.fill, c.font, c.alignment = HDR_FILL, HDR_FONT, BODY
    for r, row in enumerate(rows, 2):
        for i, v in enumerate(row, 1):
            c = ws.cell(r, i, v)
            c.alignment = BODY
            c.font = Font(size=10)
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"


def build_excel() -> Path:
    wb = Workbook()

    ws = wb.active
    ws.title = "会签总览"
    sheet(ws,
          ["条目标识", "待会签内容", "负责人", "状态", "返回码/门闩", "归属轮次",
           "验收动作摘要", "会签结论", "会签人", "日期", "备注"],
          [r + ("", "", "", "") for r in SIGNOFF_ROWS],
          [13, 52, 22, 18, 12, 10, 30, 12, 12, 12, 20])
    ws.cell(len(SIGNOFF_ROWS) + 3, 1, "说明：SIGNOFF-001..005 为 /v1 公开口会签事项；006..010 为 v1.3 语料与覆盖层事项。全部 approved 条目当前为 e2e-reviewer 占位会签，须正式重签。").font = Font(size=9, italic=True)

    ws = wb.create_sheet("规则语料")
    sheet(ws,
          ["规则标识", "族", "名称", "谓词转写（评审用，以语料为准）", "产出语义", "复核要点",
           "会签结论", "会签人", "日期"],
          [[f"{r['rule_id']}@{r['rule_version']}", r["family"],
            RULE_NOTES.get(r["rule_id"], {}).get("name", ""),
            RULE_NOTES.get(r["rule_id"], {}).get("predicate", json.dumps(r.get("predicate"), ensure_ascii=False)),
            json.dumps(r.get("outcome"), ensure_ascii=False)[:300],
            RULE_NOTES.get(r["rule_id"], {}).get("review", ""),
            "", "", ""]
           for r in RULES],
          [38, 11, 24, 60, 45, 45, 10, 10, 11])
    ws.cell(len(RULES) + 3, 1, "语料：engine/rules/corpus/core_rules.json；approved 不可改，修订走新版本 + 旧版 superseded。").font = Font(size=9, italic=True)

    ws = wb.create_sheet("法源清单")
    sheet(ws,
          ["法源标识", "名称", "文号/条文", "效力自", "效力至", "别名", "复核要点", "会签结论", "会签人", "日期"],
          [[s["id"], s["title"], s.get("document_number", ""), s.get("effective_from", ""),
            s.get("effective_to") or "现行", "、".join(s.get("aliases", [])),
            "核对效力期间、别名覆盖、新旧链声明", "", "", ""]
           for s in SOURCES],
          [40, 34, 26, 12, 12, 34, 34, 10, 10, 11])

    ws = wb.create_sheet("模板语料")
    sheet(ws,
          ["模板标识", "doc_type", "适用案型", "必填字段", "占位符要点", "状态", "会签结论", "会签人", "日期"],
          [
              ["indictment-draft@1.0.1", "indictment", "支付结算型",
               "含 amounts.payment_settlement_amount.sum 等", "占位符解析失败→blocked 不产正文",
               "approved（占位）", "", "", ""],
              ["indictment-assist@1.0.0", "indictment-assist", "帮信通用型（非支付结算）",
               "facts.defendant_name.value", "仅通用字段；新入册",
               "approved（占位）", "", "", ""],
          ],
          [24, 18, 26, 34, 36, 16, 10, 10, 11])
    ws.cell(4, 1, "策略：按案型分模板；案型→doc_type 映射与字段字典须会签（SIGNOFF-008）。").font = Font(size=9, italic=True)

    ws = wb.create_sheet("案例覆盖层")
    sheet(ws,
          ["案件", "标题", "覆盖层状态", "待审定映射项", "备注"],
          [list(r) + [""] for r in CASE_ROWS],
          [24, 40, 14, 70, 20])
    base = len(CASE_ROWS) + 3
    ws.cell(base, 1, "求值器事实键字典").font = Font(bold=True)
    for i, h in enumerate(["键", "含义", "取值", "用于"], 1):
        c = ws.cell(base + 1, i, h)
        c.fill, c.font = HDR_FILL, HDR_FONT
    for j, row in enumerate(FACT_KEYS):
        for i, v in enumerate(row, 1):
            c = ws.cell(base + 2 + j, i, v)
            c.alignment = BODY
    base += len(FACT_KEYS) + 4
    ws.cell(base, 1, "金额 kind 封闭集（ADR-0003）").font = Font(bold=True)
    for i, h in enumerate(["kind", "口径"], 1):
        c = ws.cell(base + 1, i, h)
        c.fill, c.font = HDR_FILL, HDR_FONT
    for j, row in enumerate(AMOUNT_KINDS):
        for i, v in enumerate(row, 1):
            ws.cell(base + 2 + j, i, v)

    ws = wb.create_sheet("量刑偏差")
    sheet(ws,
          ["案件", "项目", "规则计算", "案载审定", "偏差", "待确认问题"],
          [["demo-case-a-helping", "基准刑", "9.0 月（illegal_gain≥1万 档）",
            "12–18 月", "规则低 3–8.9 月",
            "基准档取值偏低还是案载裁量含未建模情节？修正走新版本规则 + 旧版 superseded"],
           ["demo-case-a-helping", "调整后", "8.1 月（坦白 -10%）", "—", "—", "调节幅度 -30%/-10%/-20% 与叠加顺序须会签"]],
          [22, 10, 30, 14, 16, 55])

    ws = wb.create_sheet("会签记录")
    sheet(ws,
          ["signoff_id", "subject_kind", "subject_key(id@version)", "reviewer", "role",
           "decision(approved/rejected)", "日期", "comment"],
          [["", "", "", "", "", "", "", ""] for _ in range(15)],
          [14, 14, 38, 14, 18, 24, 12, 40])
    ws.cell(17, 1, "回填后由工程侧逐条执行 registry.signoff()；占位会签以正式记录覆盖，历史保留。").font = Font(size=9, italic=True)

    path = OUT / f"法学会签清单-{DATE}.xlsx"
    wb.save(path)
    return path


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    w = build_word()
    x = build_excel()
    print(f"word → {w}")
    print(f"excel → {x}")


if __name__ == "__main__":
    main()
