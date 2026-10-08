import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import LegalTemporalPanel from './LegalTemporalPanel.vue'

const twoPathPayload = {
  schema_version: 'case.conviction.v2',
  status: 'blocked',
  source_resolutions: [
    {
      sourceKey: 'criminal-law',
      conduct_law: {
        title: '刑法（行为时点版本）', sourceId: 'law-1', sourceVersion: '2024.1',
        effectiveFrom: '2024-01-01', effectiveTo: '2025-12-31',
      },
      judgment_law: {
        title: '刑法（裁判时点版本）', sourceId: 'law-2', sourceVersion: '2026.1',
        effectiveFrom: '2026-01-01',
      },
    },
  ],
  temporal_paths: [
    {
      point: 'conduct',
      as_of_date: '2025-06-01',
      status: 'calculated',
      results: [{ ruleId: 'fraud', ruleVersion: '2024.1', status: 'calculated', outcome: '行为时点分支', term_months: 12, fine: { amount: 3000 }, evidence_checks: { requiredKinds: [], missingKinds: [] } }],
      dependency_snapshot: { source_versions: [{ sourceId: 'law-1', sourceVersion: '2024.1' }] },
    },
    {
      point: 'judgment',
      as_of_date: '2026-02-01',
      status: 'blocked',
      blockers: [{ code: 'MISSING_SOURCE', message: '缺少裁判时点适用法源' }],
      results: [{ ruleId: 'fraud', ruleVersion: '2026.1', status: 'blocked', term_months: 24 }],
      dependency_snapshot: { source_versions: [{ sourceId: 'law-2', sourceVersion: '2026.1' }] },
    },
  ],
}

describe('LegalTemporalPanel', () => {
  it('mounts both dated paths with their source versions and different results', () => {
    const wrapper = mount(LegalTemporalPanel, { props: { content: twoPathPayload } })
    const text = wrapper.text()
    expect(text).toContain('行为时点')
    expect(text).toContain('裁判时点')
    expect(text).toContain('2025-06-01')
    expect(text).toContain('2026-02-01')
    expect(text).toContain('2024.1')
    expect(text).toContain('2026.1')
    expect(text).toContain('刑期 12 个月')
    expect(text).toContain('罚金 3000 元')
    expect(text).toContain('行为时点分支')
  })

  it('hides numbers for a blocked path and explains that a calculated path is not selected', () => {
    const wrapper = mount(LegalTemporalPanel, { props: { content: twoPathPayload } })
    const text = wrapper.text()
    expect(text).toContain('该路径已阻断，暂不显示计算数字')
    expect(text).toContain('缺少裁判时点适用法源')
    expect(text).toContain('待人工择法的路径对照，未选为结论')
    expect(text).not.toContain('刑期 24 个月')
  })

  it('renders nothing when temporal fields are absent', () => {
    const wrapper = mount(LegalTemporalPanel, { props: { content: { status: 'calculated', rules: [] } } })
    expect(wrapper.find('[data-testid="legal-temporal-panel"]').exists()).toBe(false)
  })

  it('hides numbers when a calculated path still has blockers', () => {
    const content = JSON.parse(JSON.stringify(twoPathPayload))
    content.status = 'calculated'
    content.temporal_paths = [{
      point: 'conduct', as_of_date: '2025-06-01', status: 'calculated',
      blockers: [{ code: 'NEEDS_REVIEW', message: '需要人工核验' }],
      results: [{ ruleId: 'fraud', ruleVersion: '2024.1', status: 'calculated', term_months: 12 }],
    }]
    const wrapper = mount(LegalTemporalPanel, { props: { content } })
    expect(wrapper.text()).toContain('该路径已阻断，暂不显示计算数字')
    expect(wrapper.text()).not.toContain('刑期 12 个月')
  })

  it('defensively blocks a calculated path when nested evidence is missing', () => {
    const content = {
      status: 'calculated',
      temporal_paths: [{
        point: 'conduct', as_of_date: '2025-06-01', status: 'calculated',
        results: [{
          ruleId: 'evidence-rule', ruleVersion: '1', status: 'calculated', term_months: 12, fine: { amount: 900 },
          evidence_checks: { requiredKinds: ['服务记录'], missingKinds: ['服务记录'], unconfirmedKinds: [] },
        }],
      }],
    }
    const wrapper = mount(LegalTemporalPanel, { props: { content } })
    const text = wrapper.text()
    expect(text).toContain('该路径已阻断，暂不显示计算数字')
    expect(text).toContain('缺少必需证据类型 服务记录')
    expect(text).toContain('已阻断')
    expect(text).not.toContain('已计算')
    expect(text).not.toContain('刑期 12 个月')
    expect(text).not.toContain('罚金 900 元')
  })

  it('shows only the source key selected by a path', () => {
    const content = {
      source_resolutions: [
        { sourceKey: 'selected-law', title: '应显示法源', sourceVersion: 'v1' },
        { sourceKey: 'other-law', title: '不应显示法源', sourceVersion: 'v2' },
      ],
      temporal_paths: [{
        point: 'conduct', as_of_date: '2025-01-01', status: 'calculated',
        dependency_snapshot: { source_versions: [{ sourceKey: 'selected-law', point: 'conduct' }] },
        results: [],
      }],
    }
    const wrapper = mount(LegalTemporalPanel, { props: { content } })
    expect(wrapper.text()).toContain('应显示法源')
    expect(wrapper.text()).not.toContain('不应显示法源')
  })

  it('shows overlap candidates for the selected point when no single law is resolved', () => {
    const content = {
      source_resolutions: [{
        sourceKey: 'overlap-law', overlap: true,
        overlaps: [{ point: 'conduct', candidates: [
          { title: '候选法源甲', sourceId: 'law-a', sourceVersion: 'v1', effectiveFrom: '2024-01-01' },
          { title: '候选法源乙', sourceId: 'law-b', sourceVersion: 'v2', effectiveFrom: '2024-06-01' },
        ] }],
      }],
      temporal_paths: [{
        point: 'conduct', as_of_date: '2025-01-01', status: 'blocked',
        blockers: [{ message: '法源区间重叠' }],
        dependency_snapshot: { source_versions: [{ sourceKey: 'overlap-law', point: 'conduct' }] },
      }],
    }
    const wrapper = mount(LegalTemporalPanel, { props: { content } })
    expect(wrapper.text()).toContain('候选法源甲')
    expect(wrapper.text()).toContain('候选法源乙')
    expect(wrapper.text()).toContain('版本 v1')
    expect(wrapper.text()).toContain('版本 v2')
  })

  it('derives status from the legacy module rule shape and shows unconfirmed evidence', () => {
    const content = {
      status: 'calculated',
      temporal_paths: [{
        point: 'conduct', as_of_date: '2025-01-01', status: 'calculated',
        rules: [
          { ruleId: 'legacy-hit', ruleVersion: '1', fired: true, outcome: '命中分支' },
          { ruleId: 'legacy-idle', ruleVersion: '1', fired: false, outcome: '不应作为结论' },
        ],
      }, {
        point: 'judgment', as_of_date: '2026-01-01', status: 'calculated',
        rules: [{ ruleId: 'legacy-blocked', ruleVersion: '1', fired: true, evidence_checks: { unconfirmedKinds: ['聊天记录'], blockers: [{ code: 'RULE_EVIDENCE_UNCONFIRMED' }] } }],
      }],
    }
    const wrapper = mount(LegalTemporalPanel, { props: { content } })
    const text = wrapper.text()
    expect(text).toContain('legacy-hit@1')
    expect(text).toContain('已计算')
    expect(text).toContain('以下证据类型待核实 聊天记录')
    expect(text).toContain('legacy-idle@1')
    expect(text).toContain('不适用')
  })
})
