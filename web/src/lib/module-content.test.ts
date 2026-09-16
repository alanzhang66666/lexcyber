import { describe, expect, it } from 'vitest'
import { toAmounts, toAnalysisFacts, toBlockers, toCandidatePaths, toSentencing } from './module-content'

describe('module-content 归一化', () => {
  it('从 snake_case 提取事实（stage/verification_status/locator）', () => {
    const facts = toAnalysisFacts({
      facts: [
        { stage: '资金转移', statement: '通过第三方账户划转', verification_status: 'candidate', locator: 'paragraph:3' },
      ],
    })
    expect(facts).toHaveLength(1)
    expect(facts[0].stage).toBe('资金转移')
    expect(facts[0].statement).toBe('通过第三方账户划转')
    expect(facts[0].status).toBe('candidate')
    expect(facts[0].locator).toBe('paragraph:3')
  })

  it('候选路径同时提取支持与相反证据（并列）', () => {
    const paths = toCandidatePaths({
      analyses: {
        candidate_paths: [
          { title: '帮信', kind: 'candidate', supporting_evidence_ids: ['e1'], contrary_evidence_ids: ['e2'] },
        ],
      },
    })
    expect(paths).toHaveLength(1)
    expect(paths[0].title).toBe('帮信')
    expect(paths[0].kind).toBe('candidate')
    expect(paths[0].supporting[0].id).toBe('e1')
    expect(paths[0].contrary[0].id).toBe('e2')
  })

  it('金额口径提取 kind/value/currency，字符串数值转数字', () => {
    const amounts = toAmounts({
      amounts: [{ kind: 'account_total_flow', value: '120000', currency: 'CNY' }],
    })
    expect(amounts).toHaveLength(1)
    expect(amounts[0].kind).toBe('account_total_flow')
    expect(amounts[0].value).toBe(120000)
    expect(amounts[0].currency).toBe('CNY')
  })

  it('阻断项提取 code/path/message', () => {
    const blockers = toBlockers({
      blockers: [{ code: 'MISSING_AMOUNT', path: 'sentencing.amount', message: '缺少数额' }],
    })
    expect(blockers).toHaveLength(1)
    expect(blockers[0].code).toBe('MISSING_AMOUNT')
    expect(blockers[0].path).toBe('sentencing.amount')
    expect(blockers[0].message).toBe('缺少数额')
  })

  it('未知结构返回空数组，不抛错', () => {
    expect(toAnalysisFacts({})).toEqual([])
    expect(toCandidatePaths({})).toEqual([])
    expect(toAmounts({})).toEqual([])
    expect(toBlockers({})).toEqual([])
  })

  it('量刑结果容错提取 ruleVersion/interval/amounts/blockers', () => {
    const r = toSentencing({
      rule_version: 'V2026.2',
      interval: '3年～10年',
      amounts: [{ kind: 'crime_amount', value: 380000, currency: 'CNY' }],
    })
    expect(r.ruleVersion).toBe('V2026.2')
    expect(r.interval).toBe('3年～10年')
    expect(r.amounts).toHaveLength(1)
    expect(r.amounts[0].kind).toBe('crime_amount')
    expect(r.blockers).toEqual([])
  })
})
