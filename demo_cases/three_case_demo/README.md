# 三案演示基准包（T3）

本目录是 `LAW-01` 的机器可读交付，不是已经生效的法律结论。A、B、C 分别覆盖帮助行为、所得形成后资金处置、单位/合规/涉外连接点。原始材料来自用户提供的 `合成案例40个(1).zip` 中案例 003、010、004；每个文件都记录了归档路径和 SHA-256，以便回查。

## 当前状态

- 三个 JSON 包均通过结构、唯一 ID、引用和金额格式校验。
- 原“法学标注”统一记作 `benchmark_annotation`，只表示待核基准，不作为证据，也不等于法学负责人批准。
- 全部事实目前为 `baseline_asserted` 或 `candidate`，尚未升级为 `confirmed`。
- 每案只有一份真正的 `case_material`；第二份是标注文件，所以校验器会保留 `insufficient_evidentiary_documents` 警告。
- 三案量刑基准均为 `pending`。适配器会返回 `blocked` 和具体 blocker，不输出刑期。

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
sources = search_legal_sources("2025掩隐解释", as_of_date="2026-09-14")
blocked = calculate_case_sentencing(case_b, "actor-b-li")
```

也可直接运行 `python scripts/validate_three_case_demo.py` 输出完整校验报告；结构或引用错误时退出码为 1，法学待核和材料不足保留为 warnings。

T1 可直接把 bundle 作为内部输入映射到案件、任务和结果版本；T2 可按 `actors`、`events`、`evidence`、`facts`、`amounts`、`analyses` 和 `document_fields` 渲染。不得把 `benchmark_position`、`benchmark_disposition` 或 `baseline_asserted` 显示为已审核结论。

## 法学负责人确认后的升级顺序

1. 补齐每案第二份可定位的案件证据材料，并更新材料哈希和证据引用。
2. 把逐项确认的事实改为 `confirmed`，冲突项改为 `conflicted`，不得整包批量确认。
3. 确认行为时法、裁判时解释及 2025 新规则的时间适用关系。
4. 确认候选路径、相反证据和排除理由后，将相应分析的 `legal_review_status` 改为 `approved`。
5. 另行给出带版本、来源和适用条件的计算规则；只有规则和全部计算输入都获确认，量刑适配器才会执行。
6. 确认文书类型和正文模板后，补齐 `document_fields` 对应模板版本。
