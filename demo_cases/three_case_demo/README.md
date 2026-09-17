# 三案演示基准包（T3）

本目录是 `LAW-01` 的机器可读交付，不替代司法裁量。A、B、C 分别覆盖帮助行为、资金处置界分、单位/合规/涉外连接点。2026-09-17 根据法学团队终版清单和用户本地材料，将基准包更新为案例 011（改）、009（改）+042（改编终稿）、016；每个文件都记录了相对材料路径和 SHA-256，以便回查。

## 当前状态

- 三个 JSON 包均通过结构、唯一 ID、引用和金额格式校验。
- “输入材料”记作 `case_material`；“法学标注”和“演示案例说明”只记录核验结论，不作为案件证据。
- 法学终版清单逐项确认的事实已标记为 `confirmed`，待补信息保持 `candidate`，存在相反证据的字段保持 `conflicted`。
- A、C 的候选罪名与排除路径已按终版清单更新；B 已补入案例 042 输入材料和法学标注，并与案例 009 组成帮信/掩隐对照。
- 042 原文件是 T1 不支持上传的旧版 `.doc`，本地生成了全文一致的 `.docx` 副本；bundle 同时保存原文件哈希、转换后哈希和全文比对哈希。
- 042 原案二审维持帮信罪；补充材料是将定性和刑期改成掩隐罪的教学改编。两条路径和两组结果必须分开显示，改编刑期不得冒充真实裁判或系统计算结果。
- 三案量刑均继续为 `pending`。现有区间不是可执行规则，适配器必须返回 `blocked` 和具体 blocker，不输出刑期。
- 公开检索、量刑及分析开关继续保持关闭，不能因为数据包更新而自动启用。

## 使用

```python
from engine.adapters import (
    calculate_case_sentencing,
    load_case_bundle,
    search_legal_sources,
    validate_case_dataset,
)

report = validate_case_dataset()
case_b = load_case_bundle("B")
sources = search_legal_sources("2025掩隐解释", as_of_date="2026-09-17")
blocked = calculate_case_sentencing(case_b, "actor-b-huang")
```

也可直接运行 `python scripts/validate_three_case_demo.py` 输出完整校验报告；结构或引用错误时退出码为 1，法学待核项保留为 warnings。

联调上传真实材料时，使用：

```powershell
python scripts/import_three_case_demo.py --docs-dir "F:\1项目\111量刑预测"
```

导入器只上传 `case_material`，不会把法学标注或终版说明当作案件证据。由于公开上传接口只接受 PDF/DOCX，运行前应确认根目录存在 `042输入材料新(1).docx`；原 `.doc` 仅用于来源追溯。

T1 可直接把 bundle 作为内部输入映射到案件、任务和结果版本；T2 可按 `actors`、`events`、`evidence`、`facts`、`amounts`、`analyses` 和 `document_fields` 渲染。不得把 `benchmark_position`、`benchmark_disposition` 或 `baseline_asserted` 显示为已审核结论。

## 法学负责人确认后的升级顺序

1. 对 042“办理贷款”辩解与犯罪关联明知之间的冲突完成人工复核，并确认改编结论只能作为教学基准。
2. 对 A 的支付结算金额口径、C 的境外连接点和违法所得口径完成剩余核验。
3. 另行给出带版本、来源、起点和有序调节项的量刑计算规则；只有规则和全部计算输入都获确认，量刑适配器才会执行。
4. 解决 B 案 009 量刑文字中的区间冲突，不能从多个建议中自行选值；042 的改编刑期也不能直接转成规则。
5. 确认起诉书、量刑建议书和不起诉决定书的模板结构及版本，再补齐 `document_fields`。
6. 完成收集方式、清洗方法、许可证/授权、实质改造和脱敏措施的案例来源台账。
