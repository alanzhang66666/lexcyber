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

  it('严格读取 snake_case 候选路径，并保留排除理由、证据冲突与阻断状态', () => {
    const analysis = toV2ModuleAnalysis({
      ...CONVICTION_PAYLOAD,
      candidate_paths: [{
        id: 'cp-1', path_id: 'path-1', actor_id: 'actor-1', label: '帮信路径', charge_key: 'help_info',
        baseline_position: 'excluded', supporting_evidence_ids: ['ev-1'], contrary_evidence_ids: ['ev-2'], legal_source_ids: ['law-1'],
        rule_id: 'r-1', rule_version: '1', point: 'conduct', verification_status: 'candidate', status: 'calculated',
        exclusion_reason: '待核对主观认识', blockers: [],
      }],
    })!
    expect(analysis.candidatePaths[0].exclusionReason).toBe('待核对主观认识')
    expect(analysis.candidatePaths[0].contraryEvidenceIds).toEqual(['ev-2'])
    expect(analysis.candidatePaths[0].status).toBe('calculated')
    expect(analysis.pathDiagnostics).toEqual([])
  })

  it('畸形路径成为诊断，未知 schema 不读取路径', () => {
    const malformed = toV2ModuleAnalysis({ ...CONVICTION_PAYLOAD, candidate_paths: [{ path_id: 'p', actor_id: 'a', label: '缺少字段' }] })!
    expect(malformed.candidatePaths).toEqual([])
    expect(malformed.pathDiagnostics[0].path).toBe('candidate_paths[0]')
    expect(toV2ModuleAnalysis({ schema_version: 'case.other.v2', candidate_paths: [] })).toBeNull()
  })

  it('拒绝互相矛盾的计算状态、阻断状态与重复证据引用', () => {
    const row = {
      id: 'cp', path_id: 'p', actor_id: 'a', label: '路径', charge_key: 'charge', baseline_position: 'candidate',
      supporting_evidence_ids: ['e', 'e'], contrary_evidence_ids: [], legal_source_ids: [], rule_id: 'r', rule_version: '1',
      point: 'conduct', verification_status: 'candidate', status: 'calculated', exclusion_reason: null, blockers: [],
    }
    const duplicate = toV2ModuleAnalysis({ ...CONVICTION_PAYLOAD, candidate_paths: [row] })!
    expect(duplicate.pathDiagnostics).toHaveLength(1)
    const conflicted = toV2ModuleAnalysis({ ...CONVICTION_PAYLOAD, candidate_paths: [{ ...row, supporting_evidence_ids: [], verification_status: 'conflicted' }] })!
    expect(conflicted.pathDiagnostics[0].message).toContain('conflicted')
    const blocked = toV2ModuleAnalysis({ ...CONVICTION_PAYLOAD, candidate_paths: [{ ...row, supporting_evidence_ids: [], status: 'blocked', blockers: [{ code: 'MISSING_FACT' }] }] })!
    expect(blocked.pathDiagnostics[0].message).toContain('blocked')
  })

  it('允许同一证据在支持与相反两侧分别出现', () => {
    const path = {
      id: 'cp-cross', path_id: 'p-cross', actor_id: 'a', label: '交叉证据路径', charge_key: 'charge', baseline_position: 'candidate',
      supporting_evidence_ids: ['same-proof'], contrary_evidence_ids: ['same-proof'], legal_source_ids: [], rule_id: 'r', rule_version: '1',
      point: 'conduct', verification_status: 'candidate', status: 'calculated', exclusion_reason: null, blockers: [],
    }
    const analysis = toV2ModuleAnalysis({ ...CONVICTION_PAYLOAD, candidate_paths: [path] })!
    expect(analysis.pathDiagnostics).toEqual([])
    expect(analysis.candidatePaths[0].supportingEvidenceIds).toEqual(['same-proof'])
    expect(analysis.candidatePaths[0].contraryEvidenceIds).toEqual(['same-proof'])
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

  it('保留总体 blocked 与全部逐规则阻断，不把首条刑期当成成功结果', () => {
    const result = toSentencingResultV2({
      schema_version: 'sentencing.v2',
      status: 'blocked',
      results: [
        {
          ruleId: 'rule-calculated', ruleVersion: '1.0.0', status: 'calculated', term_months: 12,
          steps: [{ id: 'base', after_months: 12 }], blockers: [],
        },
        {
          ruleId: 'rule-blocked', ruleVersion: '2.0.0', status: 'blocked', term_months: null,
          steps: [], blockers: [{ code: 'MISSING_FACT', path: 'facts.x', message: '缺少事实' }],
        },
      ],
      blockers: [{ code: 'OVERALL_BLOCKED', message: '总体阻断' }],
      human_review_required: true,
    })
    expect(result?.status).toBe('blocked')
    expect(result?.ruleResults).toHaveLength(2)
    expect(result?.ruleResults?.[1].status).toBe('blocked')
    expect(result?.blockers?.map((item) => item.code)).toEqual(['OVERALL_BLOCKED', 'MISSING_FACT'])
    expect(result?.interval).toBeNull()
    expect(result?.steps).toEqual([])
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
