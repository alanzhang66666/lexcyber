# LexCyber 法律规则、文书模板与页面输出补充需求

版本：补充需求 V1.0 · 2026-10-10  
状态：已采纳为实施基线。本文件不表示变更已经会签或已经全部完成。

依据是 2026-10-09 法学生复核意见，以及当日对现行《网络安全法》文本的核对：主席令第六十一号，2025年10月28日通过，2026年1月1日起施行；日志留存为第二十三条第三项，真实身份信息为第二十六条。官方文本见中央网信办公布页。

## 实施边界

保留现有 v1.3 架构和已验证的事实确认、执行、注册、发布、复核、归档。已会签记录不原地修改。已应用迁移不修改。冻结比赛包不修改。`/v1` 公开口继续返回现有 `501`，默认开关不打开。新规则以新版本登记，`legal_review_status` 保持 `pending`，经法学负责人 `signoff()` 后才进入有效视图，旧版再标 `superseded`。

输出继续 `human_review_required=true`。执行状态仍是 `calculated`、`blocked`、`not_applicable`。补充规则另记业务状态 `met`、`not_met`、`unknown`、`conflicted`。事实缺失、证据未确认或执行阻断不得写成条件不满足，也不得写成罪名已被排除。

八条情节严重路径是本轮确定性范围，不宣称穷尽法释〔2019〕15号第十二条的全部情形。删除 `presumed` 作为明知终态，不取消依据客观证据审查后认定「知道」；反证可以推翻。

## 已在本批落地

| 项 | 落地位置 | 状态 |
| --- | --- | --- |
| 金额 kind 增加 `account_total_flow`、`provided_funds_amount` | ADR-0007，app `V27`，`FactsBaselineService.AMOUNT_KINDS` | 代码已加，迁移须在新环境前向执行 |
| 本人 / 非本人（含单位）账户流入分计 | `confirmedSumSelf`、`confirmedSumNonSelf` | 只读聚合，未会签 |
| 帮信构成要件、八条情节严重、掩隐界分、诈骗共犯、日志留存、实名核验 | `core_rules.json` 的 `1.1.0` | pending，不替代 1.0.x |
| 建议罪名受严重程度规则约束 | `module_analysis._apply_assist_severity_gate` | 仅当两个 1.1.0 都在同一次执行结果中才生效 |
| 《网络安全法》2025年修正 | `legal_sources.json` 的 `cn-cybersecurity-law-2025@2025-revision` | pending，生效日 2026-01-01 |

1.1.0 在播种并会签之前不参与 `active_rules`。案例 A 的 9.0 个月和坦白后 8.1 个月保持不变，说明见 `docs/demo-case-a-sentencing-note.md`。

## 规则口径

**构成要件 `rule-conviction-assist-287-2-elements@1.1.0`。** 明知只接受 `explicit`。帮助行为接受三类：`technical_support`、`payment_settlement`、`advertising_promotion`；互联网接入、服务器托管、网络存储、通讯传输归入技术支持。上游犯罪须已建立。四项里的情节严重不在本谓词里重复写阈值，而引用 `rule-conviction-assist-severity-2019-threshold@1.1.0`。两者都 `calculated` 时才写入 `recommended_charge`，并说明这是待核查的建议罪名。

**情节严重 `1.1.0`，满足任意一条。**

1. 帮助对象不少于 3 人，不再同时要求支付结算 30 万元。
2. `payment_settlement_amount` 不少于 20 万元。
3. `provided_funds_amount` 不少于 5 万元。不得用账户流入或经营收入代替。
4. `illegal_gain` 不少于 1 万元。
5. 二年内因非法利用信息网络受过行政处罚，事实键 `internet_admin_penalty_within_2y`。
6. 本人账户不少于 3 个，且 `confirmedSumSelf` 不少于 30 万元。
7. 存在非本人账户交易，且 `confirmedSumNonSelf` 不少于 30 万元。不要求三个账户。
8. 电话卡或物联网卡不少于 20 张。

**掩隐 `rule-distinction-concealment-after-upstream@1.1.0`。** 只在既遂后首次介入、无事前通谋、无持续参与时命中。命中结果是帮信时间界分线索，掩隐只作候选罪名。

**诈骗共犯 `1.1.0`。** 事前通谋加具体明知和支持行为，或既遂前稳定配合加具体明知和实质参与。概括明知不命中。

**实名 `1.1.0`。** 制度存在且实际执行才命中。确认未执行时业务状态为 `not_met`。

**日志留存 `1.1.0`。** 仍要求不少于六个月，并要求实际留存。2026年1月1日前不得用修正文本代替旧法。旧法版本尚未登记。

## 尚未落地

- 候选路径的 `candidate_paths` 声明。实施包写明支持事实键仍是设计建议，尚未按冻结事实字典审定，因此没有写入可执行路径。
- 已会签 `indictment-draft@1.0.2` 的数据库原文和内容哈希尚未从注册表回读。语料中的 `1.1.0` 是新的 pending 草稿，不代替该记录。
- 法学负责人会签、旧版 `superseded`、数据库执行 `V27`、公开能力解禁验收。

完成标准仍是：新条件能在真实执行链上计算，缺失不被视为满足或排除，文书有适用条件和阻断，页面保持辅助研判表述，法源、规则、事实、模板和会签记录可以追溯。
