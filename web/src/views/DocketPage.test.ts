import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import DocketPage from './DocketPage.vue'

afterEach(() => {
  vi.restoreAllMocks()
  sessionStorage.clear()
})

async function mountDocket(caseId: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/cases/:caseId/docket', component: DocketPage },
      { path: '/cases/:caseId/analysis', component: { template: '<div />' } },
      { path: '/cases/:caseId', component: { template: '<div />' } },
      { path: '/cases', component: { template: '<div />' } },
    ],
  })
  await router.push(`/cases/${caseId}/docket`)
  await router.isReady()
  const wrapper = mount(DocketPage, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

describe('DocketPage', () => {
  it('does not render 林某 placeholder excerpts as the open case', async () => {
    const getCase = vi.spyOn(api, 'getCase')
    const wrapper = await mountDocket('lin-128')
    expect(getCase).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('阅卷结果未接通')
    expect(wrapper.text()).not.toContain('林某')
    expect(wrapper.text()).not.toContain('境外即时通讯')
    expect(wrapper.text()).not.toContain('人民币 380,000')
    wrapper.unmount()
  })

  it('shows 未接通 for a real T1 case instead of example sentences', async () => {
    vi.spyOn(api, 'getCase').mockResolvedValue({
      id: 't1-case-9',
      title: '交接样例案',
      createdAt: 't',
      updatedAt: 't',
    })
    const wrapper = await mountDocket('t1-case-9')
    expect(wrapper.text()).toContain('交接样例案')
    expect(wrapper.text()).toContain('阅卷结果未接通')
    expect(wrapper.text()).not.toContain('林某')
    expect(wrapper.text()).not.toContain('被告人林某通过境外即时通讯软件')
    wrapper.unmount()
  })
})
