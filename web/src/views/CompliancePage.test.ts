import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, apiV2 } from '../api'
import CompliancePage from './CompliancePage.vue'

async function mountPage(caseId: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/cases/:caseId/compliance', component: CompliancePage, props: true },
      { path: '/cases/:caseId', component: { template: '<div />' } },
      { path: '/cases', component: { template: '<div />' } },
      { path: '/reviews', component: { template: '<div />' } },
    ],
  })
  await router.push(`/cases/${caseId}/compliance`)
  await router.isReady()
  const wrapper = mount(CompliancePage, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

afterEach(() => vi.restoreAllMocks())

describe('CompliancePage', () => {
  it('renders a draft module state with the case title and fact sections', async () => {
    vi.spyOn(api, 'getCase').mockResolvedValue({ id: 't1-case-9', title: '交接样例案', createdAt: 't', updatedAt: 't' })
    vi.spyOn(apiV2, 'getModuleHead').mockResolvedValue({
      caseId: 't1-case-9', module: 'compliance', streamId: 'st-1',
      latestVersionId: 'av-1', confirmedVersionId: null,
      effectivelyConfirmed: false, stale: false, staleReason: null, updatedAt: 't',
    })
    vi.spyOn(apiV2, 'getArtifactVersion').mockResolvedValue({
      artifactVersionId: 'av-1', caseId: 't1-case-9', kind: 'compliance',
      version: 1, schemaVersion: 'case.compliance.v2', outcomeStatus: 'calculated',
      payload: { status: 'calculated', rules: [] }, createdAt: 't',
    })
    const wrapper = await mountPage('t1-case-9')
    expect(wrapper.text()).toContain('交接样例案')
    expect(wrapper.text()).toContain('草稿')
    expect(wrapper.text()).toContain('合规事实梳理')
    expect(wrapper.text()).toContain('合规与风险时间线')
    wrapper.unmount()
  })

  it('points placeholder cases to the case list without calling the module API', async () => {
    const getCase = vi.spyOn(api, 'getCase')
    const getModuleHead = vi.spyOn(apiV2, 'getModuleHead')
    const wrapper = await mountPage('lin-128')
    expect(getCase).not.toHaveBeenCalled()
    expect(getModuleHead).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('请先选择真实案件')
    wrapper.unmount()
  })
})
