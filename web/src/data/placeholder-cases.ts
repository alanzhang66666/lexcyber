export type RiskLevel = 'high' | 'medium' | 'low'
export type CasePhase = 'docket' | 'analysis' | 'review' | 'materials'

export type PlaceholderDocument = {
  id: string
  group: string
  name: string
  kind: string
  pages: number
  status: 'parsed' | 'ocr' | 'pending'
  excerpt?: string
}

export type PlaceholderField = {
  id: string
  tab: 'elements' | 'evidence' | 'sources' | 'issues'
  label: string
  value: string
  confidence?: number
  locator: string
  state: 'confirmed' | 'pending' | 'conflict'
  note?: string
}

export type PlaceholderCase = {
  id: string
  shortName: string
  party: string
  caseNumber: string
  charge: string
  jurisdiction: string
  instance: string
  reviewer: string
  phase: CasePhase
  risk: RiskLevel
  updatedAt: string
  summary: string
  confirmedFields: number
  totalFields: number
  materialsDone: number
  materialsTotal: number
  attention?: string
  documents: PlaceholderDocument[]
  fields: PlaceholderField[]
  analysis: {
    statutoryRange: string
    baseline: string
    interval: string
    ruleVersion: string
    circumstances: { name: string; range: string; value: string; state: 'confirmed' | 'pending' }[]
  }
}

export const PLACEHOLDER_CASES: PlaceholderCase[] = [
  {
    id: 'lin-128',
    shortName: '林某涉嫌跨境电信网络诈骗',
    party: '林某',
    caseNumber: '（示）沪 01 刑初 128 号',
    charge: '涉嫌诈骗（电信网络）',
    jurisdiction: '上海市',
    instance: '一审',
    reviewer: '本地审核员',
    phase: 'docket',
    risk: 'medium',
    updatedAt: '今天 14:32',
    summary: '示例：犯罪嫌疑人通过境外即时通讯与收款通道，对境内被害人实施引流、话术诱导与分账。资金链路、聊天记录与平台日志尚待逐项核验。',
    confirmedFields: 8,
    totalFields: 10,
    materialsDone: 9,
    materialsTotal: 10,
    attention: '境外服务器日志待核验',
    documents: [
      { id: 'd1', group: '诉讼文书', name: '起诉书.pdf', kind: 'PDF', pages: 12, status: 'parsed', excerpt: '被告人林某通过境外即时通讯软件，以虚假投资为名诱使被害人转账。' },
      { id: 'd2', group: '诉讼文书', name: '拘留决定书.pdf', kind: 'PDF', pages: 2, status: 'parsed' },
      { id: 'd3', group: '电子证据', name: '聊天记录导出.pdf', kind: 'PDF', pages: 28, status: 'parsed' },
      { id: 'd4', group: '电子证据', name: '资金流水.xlsx', kind: 'XLS', pages: 6, status: 'parsed' },
      { id: 'd5', group: '电子证据', name: '境外服务器日志.pdf', kind: 'PDF', pages: 9, status: 'ocr' },
    ],
    fields: [
      { id: 'f1', tab: 'elements', label: '被告人', value: '林某 · 男 · 1988 年生', locator: '起诉书 P3 ¶1', state: 'confirmed', confidence: 97 },
      { id: 'f2', tab: 'elements', label: '涉案金额', value: '人民币 380,000 元', locator: '价格认定 P2 ¶4', state: 'conflict', confidence: 82, note: '资金流水另有 300,000 元记录' },
      { id: 'f3', tab: 'elements', label: '作案平台', value: '境外即时通讯 + 第三方支付', locator: '起诉书 P3 ¶4', state: 'pending', confidence: 88 },
      { id: 'f4', tab: 'evidence', label: '聊天记录', value: '诱导话术 36 段', locator: '聊天记录 P7', state: 'confirmed' },
      { id: 'f5', tab: 'evidence', label: '资金链路', value: '境内账户 → 跑分钱包', locator: '资金流水 Sheet2', state: 'pending' },
      { id: 'f6', tab: 'sources', label: '法律引用', value: '《刑法》第 266 条（示例）', locator: '起诉书 P12', state: 'pending', note: '需核对条文版本与司法解释' },
      { id: 'f7', tab: 'issues', label: '待处理', value: '境外日志 OCR 置信度较低', locator: '服务器日志 P1', state: 'pending' },
    ],
    analysis: {
      statutoryRange: '示例：三年以上十年以下有期徒刑，并处罚金（条文版本待确认）',
      baseline: '示例起点 36 个月 + 数额情节增量（未核验）',
      interval: '示例辅助区间 10～14 个月',
      ruleVersion: '规则 V2026.2（示例）',
      circumstances: [
        { name: '如实供述', range: '-10% ～ -30%', value: '-20%', state: 'confirmed' },
        { name: '退赃退赔', range: '证据 1 项待核验', value: '-10%', state: 'pending' },
        { name: '跨境环节', range: '是否作为从重情节待确认', value: '待议', state: 'pending' },
      ],
    },
  },
  {
    id: 'zhao-098',
    shortName: '赵某涉嫌帮助信息网络犯罪活动',
    party: '赵某',
    caseNumber: '（示）沪 01 刑初 098 号',
    charge: '涉嫌帮助信息网络犯罪活动',
    jurisdiction: '上海市',
    instance: '一审',
    reviewer: '本地审核员',
    phase: 'review',
    risk: 'high',
    updatedAt: '今天 10:18',
    summary: '示例：犯罪嫌疑人被指控提供收款账户与转账便利。明知程度、帮助行为与上游诈骗事实的对应关系存在争议，已进入人工复核。',
    confirmedFields: 12,
    totalFields: 12,
    materialsDone: 11,
    materialsTotal: 12,
    attention: '两套资金数额冲突',
    documents: [
      { id: 'd1', group: '诉讼文书', name: '起诉书.pdf', kind: 'PDF', pages: 10, status: 'parsed' },
      { id: 'd2', group: '电子证据', name: '银行卡流水.pdf', kind: 'PDF', pages: 14, status: 'parsed' },
      { id: 'd3', group: '电子证据', name: '聊天告知截图.pdf', kind: 'PDF', pages: 5, status: 'ocr' },
    ],
    fields: [
      { id: 'f1', tab: 'elements', label: '被告人', value: '赵某 · 男 · 1996 年生', locator: '起诉书 P2 ¶1', state: 'confirmed' },
      { id: 'f2', tab: 'elements', label: '帮助行为', value: '提供收款账户、协助转移资金', locator: '起诉书 P4', state: 'confirmed' },
      { id: 'f3', tab: 'issues', label: '明知程度', value: '聊天记录与辩解存在冲突', locator: '聊天截图 P1', state: 'conflict', note: '需对照告知内容与资金频率' },
    ],
    analysis: {
      statutoryRange: '示例：三年以下有期徒刑或者拘役，并处或者单处罚金',
      baseline: '示例起点刑待规则节点确认',
      interval: '示例辅助区间待复核后锁定',
      ruleVersion: '规则 V2026.2（示例）',
      circumstances: [
        { name: '从犯', range: '-20% ～ -50%', value: '-30%', state: 'pending' },
        { name: '退赃', range: '部分退赃', value: '-10%', state: 'pending' },
      ],
    },
  },
  {
    id: 'chen-076',
    shortName: '陈某涉嫌侵犯公民个人信息',
    party: '陈某',
    caseNumber: '（示）苏 05 刑初 076 号',
    charge: '涉嫌侵犯公民个人信息',
    jurisdiction: '苏州市',
    instance: '一审',
    reviewer: '本地审核员',
    phase: 'analysis',
    risk: 'medium',
    updatedAt: '昨天 16:20',
    summary: '示例：犯罪嫌疑人被指控批量购买、贩卖含身份与联系方式的数据包，并用于后续引流。信息条数、是否属于敏感信息及牟利数额待对照鉴定意见。',
    confirmedFields: 10,
    totalFields: 11,
    materialsDone: 8,
    materialsTotal: 9,
    documents: [
      { id: 'd1', group: '诉讼文书', name: '起诉书.pdf', kind: 'PDF', pages: 8, status: 'parsed' },
      { id: 'd2', group: '电子证据', name: '数据包目录.csv', kind: 'CSV', pages: 1, status: 'parsed' },
      { id: 'd3', group: '鉴定意见', name: '电子数据鉴定意见.pdf', kind: 'PDF', pages: 16, status: 'parsed' },
    ],
    fields: [
      { id: 'f1', tab: 'elements', label: '信息条数', value: '示例 18,600 条', locator: '鉴定意见 P6', state: 'pending', confidence: 91 },
      { id: 'f2', tab: 'elements', label: '是否敏感信息', value: '含行踪与财产信息（待确认）', locator: '鉴定意见 P8', state: 'pending' },
      { id: 'f3', tab: 'sources', label: '司法解释', value: '公民个人信息司法解释（示例版本）', locator: '规则库', state: 'confirmed' },
    ],
    analysis: {
      statutoryRange: '示例：三年以下或三年以上七年以下，视情节确认',
      baseline: '示例按信息数量进入相应法定刑档',
      interval: '示例辅助区间待情节确认后重算',
      ruleVersion: '规则 V2026.2（示例）',
      circumstances: [
        { name: '认罪认罚', range: '-10% ～ -30%', value: '-15%', state: 'confirmed' },
        { name: '违法所得', range: '数额待鉴定对照', value: '待确认', state: 'pending' },
      ],
    },
  },
]

export const PLACEHOLDER_SOURCES = [
  { id: 's1', title: '《中华人民共和国刑法》第 266 条', kind: '法律', version: '现行示例', locator: '诈骗罪' },
  { id: 's2', title: '《中华人民共和国刑法》第 287 条之二', kind: '法律', version: '现行示例', locator: '帮助信息网络犯罪活动罪' },
  { id: 's3', title: '《中华人民共和国刑法》第 253 条之一', kind: '法律', version: '现行示例', locator: '侵犯公民个人信息罪' },
  { id: 's4', title: '电信网络诈骗司法解释（示例文本）', kind: '司法解释', version: 'V2026.2 示例', locator: '数额与情节' },
  { id: 's5', title: '指导性案例（示例）· 跨境引流与资金分流', kind: '案例', version: '示例编号', locator: '类案对照' },
]

export const PLACEHOLDER_RULE_NODES = [
  { id: 'r1', title: '起点刑与数额档', detail: '示例节点：按诈骗数额或信息条数进入相应法定刑档。' },
  { id: 'r2', title: '跨境环节是否从重', detail: '示例节点：境外服务器、境外收款通道是否单独评价，待规则文本确认。' },
  { id: 'r3', title: '帮助信息网络犯罪活动的明知推定', detail: '示例节点：账号出租、频繁转账等情形的证明结构。' },
  { id: 'r4', title: '退赃、从犯、认罪认罚调节幅度', detail: '示例节点：调节区间须人工选择并记录理由。' },
]

export const LAST_CASE_KEY = 'lexcyber.last-case-id'

export function findCase(id: string) {
  return PLACEHOLDER_CASES.find((item) => item.id === id) ?? PLACEHOLDER_CASES[0]
}

export function rememberCase(id: string) {
  try {
    sessionStorage.setItem(LAST_CASE_KEY, id)
  } catch {
    /* ignore private-mode storage failures */
  }
}

export function lastCaseId() {
  try {
    return sessionStorage.getItem(LAST_CASE_KEY) || PLACEHOLDER_CASES[0].id
  } catch {
    return PLACEHOLDER_CASES[0].id
  }
}

export const PHASE_LABEL: Record<CasePhase, string> = {
  materials: '补充材料',
  docket: '要素校对',
  analysis: '量刑分析',
  review: '人工复核',
}

export const RISK_LABEL: Record<RiskLevel, string> = {
  high: '高风险',
  medium: '中风险',
  low: '低风险',
}
