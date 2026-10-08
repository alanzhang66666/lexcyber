import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AmountCard from './AmountCard.vue'
import BlockedNotice from './BlockedNotice.vue'
import CandidatePathCard from './CandidatePathCard.vue'
import FactCard from './FactCard.vue'

describe('FactCard 事实卡', () => {
  it('展示行为阶段、事实内容、待核状态与原文定位', () => {
    const wrapper = mount(FactCard, {
      props: { fact: { stage: '资金转移', statement: '通过第三方账户划转涉案资金。', locator: 'paragraph:3', status: 'candidate' } },
    })
    expect(wrapper.text()).toContain('资金转移')
    expect(wrapper.text()).toContain('通过第三方账户划转涉案资金。')
    expect(wrapper.text()).toContain('待确认')
    expect(wrapper.text()).toContain('paragraph:3')
  })

  it('baseline_asserted 显示「待法核基准」而非「已确认」', () => {
    const wrapper = mount(FactCard, {
      props: { fact: { statement: '某', status: 'baseline_asserted' } },
    })
    expect(wrapper.text()).toContain('待法核基准')
    expect(wrapper.text()).not.toContain('已确认')
  })
})

describe('CandidatePathCard 候选路径卡', () => {
  it('支持证据与相反证据并列展示，缺失一方也保留「暂无」', () => {
    const wrapper = mount(CandidatePathCard, {
      props: {
        path: {
          title: '帮助信息网络犯罪活动罪',
          kind: 'candidate',
          supporting: [{ quote: '提供支付通道', locator: 'paragraph:5' }],
          contrary: [],
        },
      },
    })
    expect(wrapper.text()).toContain('支持证据')
    expect(wrapper.text()).toContain('相反证据')
    expect(wrapper.text()).toContain('提供支付通道')
    expect(wrapper.text()).toContain('暂无')
  })

  it('未确认 excluded 路径打上「待复核排除路径」标签', () => {
    const wrapper = mount(CandidatePathCard, {
      props: { path: { title: '诈骗共犯', kind: 'excluded', summary: '保留概述', exclusionReason: '保留明确排除理由', supporting: [], contrary: [{ quote: '独立相反证据' }] } },
    })
    expect(wrapper.text()).toContain('待复核排除路径')
    expect(wrapper.text()).toContain('保留概述')
    expect(wrapper.text()).toContain('排除理由：保留明确排除理由')
    expect(wrapper.text()).toContain('独立相反证据')
  })
})

describe('AmountCard 金额口径卡', () => {
  it('账户总流水给出「≠ 犯罪所得」提示，不得互换', () => {
    const wrapper = mount(AmountCard, {
      props: { amount: { kind: 'account_total_flow', value: 120000, currency: 'CNY' } },
    })
    expect(wrapper.text()).toContain('账户总流水')
    expect(wrapper.text()).toContain('120,000 CNY')
    expect(wrapper.text()).toContain('账户总流水 ≠ 犯罪所得')
  })

  it('未分类金额保持待确认提示', () => {
    const wrapper = mount(AmountCard, {
      props: { amount: { kind: 'unclassified_amount', value: null } },
    })
    expect(wrapper.text()).toContain('未分类金额')
    expect(wrapper.text()).toContain('保持「待确认」')
  })
})

describe('BlockedNotice 阻断提示', () => {
  it('展示阻断项 code/message，不当作系统预测', () => {
    const wrapper = mount(BlockedNotice, {
      props: { blockers: [{ code: 'MISSING_AMOUNT', path: 'sentencing.amount', message: '缺少犯罪数额口径' }] },
    })
    expect(wrapper.text()).toContain('量刑结果待确认')
    expect(wrapper.text()).toContain('MISSING_AMOUNT')
    expect(wrapper.text()).toContain('缺少犯罪数额口径')
    expect(wrapper.text()).toContain('不作为系统预测')
  })

  it('无阻断项时不渲染', () => {
    const wrapper = mount(BlockedNotice, { props: { blockers: [] } })
    expect(wrapper.text()).toBe('')
  })
})
