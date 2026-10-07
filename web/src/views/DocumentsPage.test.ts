import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, apiV2 } from '../api'
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

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  vi.useRealTimers()
  localStorage.clear()
})

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

  it('refreshes drafts for the actual case rather than the click event', async () => {
    vi.spyOn(api, 'getCase').mockResolvedValue({ id: 'case-refresh', title: '刷新案件', createdAt: 't', updatedAt: 't' })
    const list = vi.spyOn(api, 'listCaseDrafts').mockResolvedValue({ items: [] })
    const wrapper = await mountPage('case-refresh')
    list.mockClear()
    await wrapper.findAll('button').find(item => item.text() === '刷新')!.trigger('click')
    await flushPromises()
    expect(list).toHaveBeenCalledExactlyOnceWith('case-refresh')
    wrapper.unmount()
  })

  it('blocks submit when the body contains 【待补充】', async () => {
    vi.spyOn(api, 'getCase').mockResolvedValue({ id: 't1-case-9', title: '交接样例案', createdAt: 't', updatedAt: 't' })
    vi.spyOn(api, 'listCaseDrafts').mockResolvedValue({
      items: [{ id: 'd1', caseId: 't1-case-9', draftType: '审查报告', body: '事实部分【待补充】', version: 1, updatedAt: '2026-09-16T00:00:00Z' }],
    })
    const wrapper = await mountPage('t1-case-9')
    expect(wrapper.text()).toContain('正文含未解析占位')
    const submit = wrapper.findAll('button').find((b) => b.text().includes('提交人工复核'))
    expect(submit?.attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('downloads a manual draft through its immutable artifact version', async () => {
    vi.spyOn(api, 'getCase').mockResolvedValue({ id: 't1-case-9', title: '交接样例案', createdAt: 't', updatedAt: 't' })
    vi.spyOn(api, 'listCaseDrafts').mockResolvedValue({
      items: [{
        id: 'd1', caseId: 't1-case-9', draftType: '审查报告', body: '正文内容', version: 2,
        updatedAt: '2026-09-16T00:00:00Z', artifactVersionId: 'artifact-immutable-2',
      }],
    })
    const exportDocx = vi.spyOn(apiV2, 'exportArtifactDocx').mockResolvedValue({
      blob: new Blob(['PK'], { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' }),
      filename: '审查报告.docx',
    })
    vi.stubGlobal('URL', { ...URL, createObjectURL: vi.fn(() => 'blob:docx'), revokeObjectURL: vi.fn() })
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    const wrapper = await mountPage('t1-case-9')

    const button = wrapper.findAll('button').find((item) => item.text().includes('下载辅助稿'))
    expect(button?.attributes('disabled')).toBeUndefined()
    await button!.trigger('click')
    await flushPromises()

    expect(exportDocx).toHaveBeenCalledWith('t1-case-9', 'artifact-immutable-2')
    expect(click).toHaveBeenCalled()
    wrapper.unmount()
  })

  it('retries after a failed load without treating the click event as a generation', async () => {
    const getCase = vi.spyOn(api, 'getCase')
      .mockRejectedValueOnce(new Error('暂时不可用'))
      .mockResolvedValue({ id: 'case-retry', title: '重试案件', createdAt: 't', updatedAt: 't' })
    vi.spyOn(api, 'listCaseDrafts').mockResolvedValue({ items: [] })
    const wrapper = await mountPage('case-retry')
    expect(wrapper.text()).toContain('暂时不可用')
    await wrapper.find('button.button-quiet').trigger('click')
    await flushPromises()
    expect(getCase).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('重试案件')
    expect(wrapper.text()).not.toContain('暂时不可用')
    wrapper.unmount()
  })

  it('downloads the rendered artifact by its exact immutable UUID and revokes the object URL', async () => {
    vi.spyOn(api, 'getCase').mockResolvedValue({ id: 'case-render', title: '渲染案件', createdAt: 't', updatedAt: 't' })
    vi.spyOn(api, 'listCaseDrafts').mockResolvedValue({ items: [] })
    vi.spyOn(apiV2, 'listDraftStreams').mockResolvedValue({ items: [{ docType: 'indictment', latestVersionId: 'latest-pointer' }] })
    vi.spyOn(apiV2, 'getArtifactVersion').mockResolvedValue({
      artifactVersionId: 'artifact-exact-uuid', streamId: 'stream-1', caseId: 'case-render', kind: 'draft',
      scopeKey: 'draft:indictment', version: 4, schemaVersion: 'draft.v2', outcomeStatus: 'calculated',
      payload: { schema_version: 'draft.v2', status: 'rendered', doc_type: 'indictment', body: '渲染正文', unresolved: [] },
      blockers: [], dependencySnapshot: {}, outputHash: 'sha256:x', createdAt: 't',
    })
    const exportDocx = vi.spyOn(apiV2, 'exportArtifactDocx').mockResolvedValue({
      blob: new Blob(['PK'], { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' }), filename: 'indictment.docx',
    })
    const createObjectURL = vi.fn(() => 'blob:rendered')
    const revokeObjectURL = vi.fn()
    vi.stubGlobal('URL', { createObjectURL, revokeObjectURL })
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    const wrapper = await mountPage('case-render')
    const button = wrapper.findAll('button').find((item) => item.text().includes('下载辅助稿'))
    expect(button?.attributes('disabled')).toBeUndefined()
    vi.useFakeTimers()
    await button!.trigger('click')
    await flushPromises()
    vi.runAllTimers()
    expect(exportDocx).toHaveBeenCalledWith('case-render', 'artifact-exact-uuid')
    expect(createObjectURL).toHaveBeenCalledOnce()
    expect(click).toHaveBeenCalledOnce()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:rendered')
    wrapper.unmount()
  })

  it('keeps rendered downloads disabled for blocked artifacts', async () => {
    vi.spyOn(api, 'getCase').mockResolvedValue({ id: 'case-blocked', title: '阻断案件', createdAt: 't', updatedAt: 't' })
    vi.spyOn(api, 'listCaseDrafts').mockResolvedValue({ items: [] })
    vi.spyOn(apiV2, 'listDraftStreams').mockResolvedValue({ items: [{ docType: 'indictment', latestVersionId: 'blocked-version' }] })
    vi.spyOn(apiV2, 'getArtifactVersion').mockResolvedValue({
      artifactVersionId: 'artifact-blocked', streamId: 'stream-1', caseId: 'case-blocked', kind: 'draft',
      scopeKey: 'draft:indictment', version: 1, schemaVersion: 'draft.v2', outcomeStatus: 'blocked',
      payload: { schema_version: 'draft.v2', status: 'blocked', doc_type: 'indictment', body: '', unresolved: [{ code: 'MISSING_FACT' }] },
      blockers: [{ code: 'MISSING_FACT' }], dependencySnapshot: {}, outputHash: 'sha256:x', createdAt: 't',
    })
    const exportDocx = vi.spyOn(apiV2, 'exportArtifactDocx')
    const wrapper = await mountPage('case-blocked')
    const button = wrapper.findAll('button').find((item) => item.text().includes('下载辅助稿'))
    expect(button?.attributes('disabled')).toBeDefined()
    expect(exportDocx).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('keeps calculated rendered drafts with unresolved placeholders out of downloads', async () => {
    vi.spyOn(api, 'getCase').mockResolvedValue({ id: 'case-placeholder', title: '占位案件', createdAt: 't', updatedAt: 't' })
    vi.spyOn(api, 'listCaseDrafts').mockResolvedValue({ items: [] })
    vi.spyOn(apiV2, 'listDraftStreams').mockResolvedValue({ items: [{ docType: 'indictment', latestVersionId: 'placeholder-version' }] })
    vi.spyOn(apiV2, 'getArtifactVersion').mockResolvedValue({
      artifactVersionId: 'artifact-placeholder', streamId: 'stream-1', caseId: 'case-placeholder', kind: 'draft',
      scopeKey: 'draft:indictment', version: 2, schemaVersion: 'draft.v2', outcomeStatus: 'calculated',
      payload: { schema_version: 'draft.v2', status: 'rendered', doc_type: 'indictment', body: '待核验【金额】', unresolved: [] },
      blockers: [], dependencySnapshot: {}, outputHash: 'sha256:x', createdAt: 't',
    })
    const exportDocx = vi.spyOn(apiV2, 'exportArtifactDocx')
    const wrapper = await mountPage('case-placeholder')
    const button = wrapper.findAll('button').find((item) => item.text().includes('下载辅助稿'))
    expect(button?.attributes('disabled')).toBeDefined()
    expect(exportDocx).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('does not let a delayed old-case download click after switching cases', async () => {
    vi.spyOn(api, 'getCase').mockImplementation(async (id) => ({ id, title: id === 'case-a' ? '旧案件' : '新案件', createdAt: 't', updatedAt: 't' }))
    vi.spyOn(api, 'listCaseDrafts').mockImplementation(async (id) => ({ items: [{
      id: `draft-${id}`, caseId: id, draftType: '报告', body: '正文', version: 1, updatedAt: 't', artifactVersionId: `artifact-${id}`,
    }] }))
    let resolveExport!: (result: { blob: Blob; filename: string }) => void
    const exportDocx = vi.spyOn(apiV2, 'exportArtifactDocx').mockReturnValue(new Promise((resolve) => { resolveExport = resolve }))
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/cases/:caseId/documents', component: DocumentsPage, props: true },
        { path: '/cases/:caseId', component: { template: '<div />' } },
        { path: '/cases', component: { template: '<div />' } },
      ],
    })
    await router.push('/cases/case-a/documents')
    await router.isReady()
    const wrapper = mount(DocumentsPage, { global: { plugins: [router] } })
    await flushPromises()
    const download = wrapper.findAll('button').find((item) => item.text().includes('下载辅助稿'))
    await download!.trigger('click')
    await router.push('/cases/case-b/documents')
    await flushPromises()
    expect(wrapper.text()).toContain('新案件')
    const newDownload = wrapper.findAll('button').find((item) => item.text().includes('下载辅助稿'))
    expect(newDownload?.attributes('disabled')).toBeUndefined()
    resolveExport({ blob: new Blob(['PK']), filename: 'old.docx' })
    await flushPromises()
    expect(exportDocx).toHaveBeenCalledWith('case-a', 'artifact-case-a')
    expect(click).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('shows export failures in the current case', async () => {
    vi.spyOn(api, 'getCase').mockResolvedValue({ id: 'case-error', title: '下载错误案', createdAt: 't', updatedAt: 't' })
    vi.spyOn(api, 'listCaseDrafts').mockResolvedValue({ items: [{
      id: 'draft-error', caseId: 'case-error', draftType: '报告', body: '正文', version: 1, updatedAt: 't', artifactVersionId: 'artifact-error',
    }] })
    vi.spyOn(apiV2, 'exportArtifactDocx').mockRejectedValue(new Error('导出服务暂不可用'))
    const wrapper = await mountPage('case-error')
    await wrapper.findAll('button').find((item) => item.text().includes('下载辅助稿'))!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('导出服务暂不可用')
    wrapper.unmount()
  })

  it('does not apply a delayed old-case response after route change', async () => {
    let resolveCase!: (value: { id: string; title: string; createdAt: string; updatedAt: string }) => void
    const firstCase = new Promise<{ id: string; title: string; createdAt: string; updatedAt: string }>((resolve) => { resolveCase = resolve })
    const getCase = vi.spyOn(api, 'getCase')
      .mockReturnValueOnce(firstCase)
      .mockResolvedValue({ id: 'case-b', title: '新案件', createdAt: 't', updatedAt: 't' })
    vi.spyOn(api, 'listCaseDrafts').mockResolvedValue({ items: [] })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/cases/:caseId/documents', component: DocumentsPage, props: true },
        { path: '/cases/:caseId', component: { template: '<div />' } },
        { path: '/cases', component: { template: '<div />' } },
      ],
    })
    await router.push('/cases/case-a/documents')
    await router.isReady()
    const wrapper = mount(DocumentsPage, { global: { plugins: [router] } })
    await router.push('/cases/case-b/documents')
    await flushPromises()
    resolveCase({ id: 'case-a', title: '旧案件', createdAt: 't', updatedAt: 't' })
    await flushPromises()

    expect(getCase).toHaveBeenCalledWith('case-a')
    expect(wrapper.text()).toContain('新案件')
    expect(wrapper.text()).not.toContain('旧案件')
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
