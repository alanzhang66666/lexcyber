import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import AnalysisPage from './AnalysisPage.vue'

afterEach(() => {
  vi.restoreAllMocks()
  sessionStorage.clear()
})

async function mountAnalysis(caseId: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/cases/:caseId/analysis', component: AnalysisPage },
      { path: '/cases/:caseId', component: { template: '<div />' } },
      { path: '/cases', component: { template: '<div />' } },
      { path: '/reviews', component: { template: '<div />' } },
    ],
  })
  await router.push(`/cases/${caseId}/analysis`)
  await router.isReady()
  const wrapper = mount(AnalysisPage, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

describe('AnalysisPage', () => {
  it('does not render placeholder sentencing ranges as results', async () => {
    const getCase = vi.spyOn(api, 'getCase')
    const wrapper = await mountAnalysis('lin-128')
    expect(getCase).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('量刑结果未接通')
    expect(wrapper.text()).not.toContain('林某')
    expect(wrapper.text()).not.toContain('三年以上十年以下')
    expect(wrapper.text()).not.toContain('示例起点 36 个月')
    expect(wrapper.text()).not.toContain('规则 V2026.2')
    wrapper.unmount()
  })

  it('keeps a real T1 case title without inventing an interval', async () => {
    vi.spyOn(api, 'getCase').mockResolvedValue({
      id: 't1-case-9',
      title: '交接样例案',
      createdAt: 't',
      updatedAt: 't',
    })
    const wrapper = await mountAnalysis('t1-case-9')
    expect(wrapper.text()).toContain('交接样例案')
    expect(wrapper.text()).toContain('量刑结果未接通')
    expect(wrapper.text()).not.toContain('10～14 个月')
    wrapper.unmount()
  })
})
