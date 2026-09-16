import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import DocumentsPage from './DocumentsPage.vue'

async function mountPage(caseId: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/cases/:caseId/documents', component: DocumentsPage, props: true },
      { path: '/cases/:caseId', component: { template: '<div />' } },
      { path: '/cases', component: { template: '<div />' } },
    ],
  })
  await router.push(`/cases/${caseId}/documents`)
  await router.isReady()
  const wrapper = mount(DocumentsPage, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

afterEach(() => vi.restoreAllMocks())

describe('DocumentsPage', () => {
  it('renders the draft list and preview', async () => {
    vi.spyOn(api, 'getCase').mockResolvedValue({ id: 't1-case-9', title: '交接样例案', createdAt: 't', updatedAt: 't' })
    vi.spyOn(api, 'listCaseDrafts').mockResolvedValue({
      items: [{ id: 'd1', caseId: 't1-case-9', draftType: '审查报告', body: '正文内容', version: 1, updatedAt: '2026-09-16T00:00:00Z' }],
    })
    const wrapper = await mountPage('t1-case-9')
    expect(wrapper.text()).toContain('审查报告')
    expect(wrapper.text()).toContain('正文内容')
    expect(wrapper.text()).toContain('v1')
    wrapper.unmount()
  })

  it('blocks submit when the body contains 【待补充】', async () => {
    vi.spyOn(api, 'getCase').mockResolvedValue({ id: 't1-case-9', title: '交接样例案', createdAt: 't', updatedAt: 't' })
    vi.spyOn(api, 'listCaseDrafts').mockResolvedValue({
      items: [{ id: 'd1', caseId: 't1-case-9', draftType: '审查报告', body: '事实部分【待补充】', version: 1, updatedAt: '2026-09-16T00:00:00Z' }],
    })
    const wrapper = await mountPage('t1-case-9')
    expect(wrapper.text()).toContain('正文含【待补充】占位')
    const submit = wrapper.findAll('button').find((b) => b.text().includes('提交人工复核'))
    expect(submit?.attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('points placeholder cases to the case list without calling the draft API', async () => {
    const getCase = vi.spyOn(api, 'getCase')
    const listDrafts = vi.spyOn(api, 'listCaseDrafts')
    const wrapper = await mountPage('lin-128')
    expect(getCase).not.toHaveBeenCalled()
    expect(listDrafts).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('请先选择真实案件')
    wrapper.unmount()
  })
})
