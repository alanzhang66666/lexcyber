import { describe, expect, it } from 'vitest'
import {
  toFactsVersionAmounts,
  toSentencingResultV2,
  toV2Draft,
  toV2ModuleAnalysis,
  toV2Sentencing,
  v2Blockers,
  v2SchemaOf,
} from './module-content-v2'

const CONVICTION_PAYLOAD = {
  schema_version: 'case.conviction.v2',
  module: 'conviction',
  status: 'calculated',
  case_id: 'case-1',
  facts_version_id: 'fv-1',
  rules: [
    {
      ruleId: 'rule-elements', ruleVersion: '1.0.0', family: 'conviction', fired: true,
      outcome: { charge: '帮助信息网络犯罪活动罪' },
      sourceIds: ['src-1'],
      trace: [
        { path: 'facts.knowledge_of_crime.value', op: 'eq', expected: true, found: true, actual: 'true', result: true },
      ],
      contentHash: 'h1',
    },
    {
      ruleId: 'rule-distinction', ruleVersion: '1.0.0', family: 'distinction', fired: false,
      outcome: null, sourceIds: [], trace: [], contentHash: 'h2',
    },
  ],
  blockers: [],
  divergence: [],
  human_review_required: true,
  generated_at: '2026-09-26T00:00:00Z',
}

describe('module-content-v2 严格读取', () => {
  it('schema_version 识别', () => {
    expect(v2SchemaOf(CONVICTION_PAYLOAD)).toBe('case.conviction.v2')
    expect(v2SchemaOf({})).toBeNull()
    expect(v2SchemaOf(null)).toBeNull()
  })

  it('case.conviction.v2 → 规则结果', () => {
    const analysis = toV2ModuleAnalysis(CONVICTION_PAYLOAD)
    expect(analysis).not.toBeNull()
    expect(analysis!.status).toBe('calculated')
    expect(analysis!.rules).toHaveLength(2)
    expect(analysis!.rules[0].fired).toBe(true)
    expect(analysis!.rules[0].outcomeSummary).toBe('帮助信息网络犯罪活动罪')
    expect(analysis!.rules[0].trace[0].result).toBe(true)
    expect(analysis!.rules[1].fired).toBe(false)
    expect(analysis!.humanReviewRequired).toBe(true)
  })

  it('未知 schema 一律返回 null，不猜读', () => {
    expect(toV2ModuleAnalysis({ schema_version: 'case.module.v1', rules: [] })).toBeNull()
    expect(toV2ModuleAnalysis({ status: 'calculated' })).toBeNull()
    expect(toV2Sentencing({ schema_version: 'case.conviction.v2' } as never)).toBeNull()
    expect(toV2Draft({ schema_version: 'sentencing.v2' })).toBeNull()
    expect(toSentencingResultV2({ schema_version: 'draft.v2' })).toBeNull()
  })

  it('sentencing.v2 → SentencingResultPanel 展示类型', () => {
    const result = toSentencingResultV2({
      schema_version: 'sentencing.v2',
      module: 'sentencing',
      status: 'calculated',
      results: [{
        ruleId: 'rule-sentencing-assist-base', ruleVersion: '1.0.1', status: 'calculated',
        term_months: 10.8, fine: { amount: 5000 },
        steps: [
          { id: 'base', operation: 'base_tier', before_months: null, delta_months: null, after_months: 12 },
          { id: 'frank', operation: 'percent_of_base', direction: 'decrease',
            before_months: 12, delta_months: -1.2, after_months: 10.8, source_ids: ['刑67'] },
          { id: 'surrender', operation: 'skipped', reason: 'when predicate not fired',
            before_months: null, delta_months: null, after_months: 10.8 },
        ],
        blockers: [],
      }],
      blockers: [],
      human_review_required: true,
    })
    expect(result).not.toBeNull()
    expect(result!.ruleVersion).toBe('rule-sentencing-assist-base@1.0.1')
    expect(result!.interval).toContain('10.8 个月')
    expect(result!.interval).toContain('罚金')
    expect(result!.steps![0].value).toBe('12 个月')
    expect(result!.steps![1].value).toBe('12 个月 → 10.8 个月')
    expect(result!.steps![2].detail).toBe('when predicate not fired')
  })

  it('sentencing.v2 blocked → 阻断项透传', () => {
    const result = toSentencingResultV2({
      schema_version: 'sentencing.v2',
      status: 'blocked',
      results: [],
      blockers: [{ code: 'BASE_UNRESOLVED', path: 'calculation.base_tiers', message: '无命中基准档' }],
      human_review_required: true,
    })
    expect(result!.blockers![0].code).toBe('BASE_UNRESOLVED')
    expect(result!.interval).toBeNull()
  })

  it('draft.v2 → 正文与未解析项', () => {
    const rendered = toV2Draft({
      schema_version: 'draft.v2', status: 'rendered', doc_type: 'indictment-assist', body: '正文',
      unresolved: [],
    })
    expect(rendered!.status).toBe('rendered')
    expect(rendered!.docType).toBe('indictment-assist')
    expect(rendered!.body).toBe('正文')

    const blocked = toV2Draft({
      schema_version: 'draft.v2', status: 'blocked', doc_type: 'indictment-draft', body: null,
      unresolved: [{ path: 'amounts.payment_settlement_amount.sum', reason: 'unresolved_or_null' }],
    })
    expect(blocked!.body).toBe('')
    expect(blocked!.unresolved[0].path).toBe('amounts.payment_settlement_amount.sum')
  })

  it('FactsVersion payload → entities.amounts', () => {
    const amounts = toFactsVersionAmounts({
      items: [],
      entities: {
        amounts: [
          { id: 'a1', kind: 'illegal_gain', label: '违法所得', value: 30000, currency: 'CNY', verificationStatus: 'confirmed' },
          { id: 'a2', kind: 'crime_amount', value: '960000', verificationStatus: 'baseline_asserted' },
        ],
      },
    })
    expect(amounts).toHaveLength(2)
    expect(amounts[0].kind).toBe('illegal_gain')
    expect(amounts[0].value).toBe(30000)
    expect(amounts[0].status).toBe('confirmed')
    expect(amounts[1].value).toBe(960000)
    expect(toFactsVersionAmounts({})).toEqual([])
    expect(toFactsVersionAmounts({ entities: 'nope' })).toEqual([])
  })

  it('v2Blockers 合并 blockers + unresolved', () => {
    const items = v2Blockers({
      blockers: [{ code: 'X', path: 'p1', message: 'm' }],
      unresolved: [{ path: 'p2', reason: 'unresolved_or_null' }],
    })
    expect(items).toHaveLength(2)
    expect(items[1].reason).toBe('unresolved_or_null')
  })
})
