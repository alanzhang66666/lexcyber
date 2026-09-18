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
    expect(wrapper.text()).not.toContain('林某')
    expect(wrapper.text()).not.toContain('境外即时通讯')
    expect(wrapper.text()).not.toContain('人民币 380,000')
    wrapper.unmount()
  })

  it('shows empty materials for a real T1 case instead of example sentences', async () => {
    vi.spyOn(api, 'getCase').mockResolvedValue({
      id: 't1-case-9',
      title: '交接样例案',
      createdAt: 't',
      updatedAt: 't',
    })
    vi.spyOn(api, 'listDocuments').mockResolvedValue({ items: [], page: 0, size: 100, total: 0 })
    const wrapper = await mountDocket('t1-case-9')
    expect(wrapper.text()).toContain('交接样例案')
    expect(wrapper.text()).toContain('暂无材料')
    expect(wrapper.text()).not.toContain('林某')
    expect(wrapper.text()).not.toContain('被告人林某通过境外即时通讯软件')
    wrapper.unmount()
  })

  it('loads the parse result of the selected document', async () => {
    vi.spyOn(api, 'getCase').mockResolvedValue({
      id: 't1-case-9',
      title: '交接样例案',
      createdAt: 't',
      updatedAt: 't',
    })
    vi.spyOn(api, 'listDocuments').mockResolvedValue({
      items: [
        {
          id: 'doc-1',
          caseId: 't1-case-9',
          filename: '阅卷材料.docx',
          contentType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
          size: 100,
          role: 'input',
          parseStatus: 'completed',
          parseTaskId: 'task-p1',
          createdAt: 't',
        },
      ],
      page: 0,
      size: 100,
      total: 1,
    })
    const getTaskResult = vi.spyOn(api, 'getTaskResult').mockResolvedValue({
      resultId: 'res-p1',
      version: 1,
      type: 'workflow.output',
      contentHash: 'h',
      content: {
        schemaVersion: 'document.parse.v1',
        documentId: 'doc-1',
        format: 'docx',
        paragraphs: [{ paragraph: 1, text: '第一段正文', locator: 'paragraph:1' }],
      },
    })
    const wrapper = await mountDocket('t1-case-9')
    await flushPromises()
    expect(getTaskResult).toHaveBeenCalledWith('task-p1')
    expect(wrapper.text()).toContain('阅卷材料.docx')
    expect(wrapper.text()).toContain('第一段正文')
    expect(wrapper.text()).toContain('paragraph:1')
    wrapper.unmount()
  })
})
