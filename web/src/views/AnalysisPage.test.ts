import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api, apiV2 } from '../api'
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
  beforeEach(() => {
    vi.spyOn(api, 'listReviews').mockResolvedValue({ items: [], page: 0, size: 100, total: 0 })
  })
  it('does not render placeholder sentencing ranges as results', async () => {
    const getCase = vi.spyOn(api, 'getCase')
    const wrapper = await mountAnalysis('lin-128')
    expect(getCase).not.toHaveBeenCalled()
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
    expect(wrapper.text()).toContain('尚未运行量刑分析')
    expect(wrapper.text()).not.toContain('10～14 个月')
    wrapper.unmount()
  })

  it('dispatches sentencing through /v2 and renders the calculated result', async () => {
    vi.spyOn(api, 'getCase').mockResolvedValue({
      id: 'srv-c',
      title: 'C 单位涉外案',
      createdAt: 't',
      updatedAt: 't',
    })
    const getFactsHead = vi.spyOn(apiV2, 'getFactsHead').mockResolvedValue({
      caseId: 'srv-c', confirmedFactsVersionId: null, nextVersion: 2,
      stale: false, updatedAt: null,
    })
    const dispatch = vi.spyOn(apiV2, 'dispatchModuleExecution').mockResolvedValue({
      taskId: 'task-1', executionId: 'e', status: 'queued', module: 'sentencing',
    })
    vi.spyOn(api, 'getTask').mockResolvedValue({
      id: 'task-1',
      requestId: 'r',
      executionId: 'e',
      caseId: 'srv-c',
      status: 'waiting_review',
      currentStage: 'sentencing',
      result: { resultId: 'res-1', version: 1, type: 'workflow.output' },
      errorCode: null,
      error: null,
      createdAt: 't',
      updatedAt: 't',
    })
    vi.spyOn(api, 'getTaskResult').mockResolvedValue({
      resultId: 'res-1',
      version: 1,
      type: 'workflow.output',
      contentHash: 'h',
      content: {
        caseId: 'srv-c',
        datasetCaseId: 'C',
        actorId: 'actor-c-jia',
        analysisStatus: 'calculated',
        calculationMode: 'reviewed_disposition_replay',
        ruleVersion: 'demo-c-jia-v1',
        termRangeMonths: [8, 14],
        fineRangeCny: [8000, 15000],
        steps: [{ id: 'adj-1', operation: 'reviewed_factor', direction: 'decrease', value: 0.2, source_ids: ['src-1'] }],
        inputSnapshot: { 'amount-c-illegal-gain': 118000 },
        blockers: [],
        warnings: ['replays reviewed disposition'],
        humanReviewRequired: true,
      },
    })
    const wrapper = await mountAnalysis('srv-c')
    const runButton = wrapper.findAll('button').find((b) => b.text().includes('运行量刑分析'))
    expect(runButton).toBeTruthy()
    await runButton!.trigger('click')
    await flushPromises()
    expect(dispatch).toHaveBeenCalledWith('srv-c', 'sentencing')
    expect(wrapper.text()).toContain('8 个月')
    expect(wrapper.text()).toContain('14 个月')
    expect(wrapper.text()).toContain('罚金')
    expect(wrapper.text()).toContain('待人工复核')
    expect(getFactsHead).toHaveBeenCalledWith('srv-c')
    wrapper.unmount()
  })
})
