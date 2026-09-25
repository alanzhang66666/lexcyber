import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import SentencingResultPanel from './SentencingResultPanel.vue'

describe('SentencingResultPanel', () => {
  it('renders rule version, interval, and amounts', () => {
    const wrapper = mount(SentencingResultPanel, {
      props: {
        result: {
          ruleVersion: 'V2026.2',
          interval: '3年～10年',
          amounts: [{ kind: 'crime_amount', value: 380000, currency: 'CNY' }],
        },
      },
    })
    expect(wrapper.text()).toContain('规则 V2026.2')
    expect(wrapper.text()).toContain('3年～10年')
    expect(wrapper.text()).toContain('犯罪数额')
    expect(wrapper.text()).toContain('380,000 CNY')
    wrapper.unmount()
  })

  it('blocked 时只展示阻断项，不展示刑期区间', () => {
    const wrapper = mount(SentencingResultPanel, {
      props: {
        result: {
          interval: '3年～10年',
          blockers: [{ code: 'MISSING_AMOUNT', message: '缺少犯罪数额口径' }],
        },
      },
    })
    expect(wrapper.text()).toContain('量刑结果待确认')
    expect(wrapper.text()).toContain('MISSING_AMOUNT')
    expect(wrapper.text()).not.toContain('3年～10年')
    wrapper.unmount()
  })
})
