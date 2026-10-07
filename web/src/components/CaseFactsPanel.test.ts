import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiV2 } from '../api'
import CaseFactsPanel from './CaseFactsPanel.vue'

afterEach(() => vi.restoreAllMocks())

describe('CaseFactsPanel facts version workflow', () => {
  it('lists history, compares versions, and clones without confirming a new head', async () => {
    vi.spyOn(apiV2, 'getFactsEntities').mockResolvedValue({ caseId: 'case-7', items: [{ key: '事实', value: '旧' }], entities: {} })
    vi.spyOn(apiV2, 'getFactsHead').mockResolvedValue({ caseId: 'case-7', confirmedFactsVersionId: 'fv-1', updatedAt: null })
    vi.spyOn(apiV2, 'listFactsVersions').mockResolvedValue({ items: [
      { factsVersionId: 'fv-1', caseId: 'case-7', version: 1, status: 'confirmed', contentHash: 'h1', createdAt: 't1' },
      { factsVersionId: 'fv-2', caseId: 'case-7', version: 2, status: 'draft', contentHash: 'h2', createdAt: 't2' },
    ] })
    vi.spyOn(apiV2, 'getFactsVersion').mockResolvedValue({
      factsVersionId: 'fv-1', caseId: 'case-7', version: 1, status: 'confirmed', contentHash: 'h1', createdAt: 't1',
      payload: { items: [{ key: '事实', value: '旧' }], entities: {} },
    })
    const diff = vi.spyOn(apiV2, 'diffFactsVersion').mockResolvedValue({
      caseId: 'case-7', fromFactsVersionId: 'fv-1', toFactsVersionId: 'fv-2',
      sections: { facts: { added: [{ key: '事实', value: '新' }], removed: [], changed: [] } },
    })
    const clone = vi.spyOn(apiV2, 'cloneFactsVersion').mockResolvedValue({ caseId: 'case-7', items: [], entities: {} })
    const wrapper = mount(CaseFactsPanel, { props: { caseId: 'case-7' } })
    await flushPromises()

    expect(wrapper.text()).toContain('事实版本历史')
    expect(wrapper.text()).toContain('fv-1')
    expect(wrapper.text()).toContain('回写只更新工作副本')
    const selects = wrapper.findAll('select')
    await selects[0].setValue('fv-2')
    await selects[1].setValue('fv-1')
    await wrapper.findAll('button').find((button) => button.text() === '对比版本')!.trigger('click')
    await flushPromises()
    expect(diff).toHaveBeenCalledWith('case-7', 'fv-2', 'fv-1')
    expect(wrapper.text()).toContain('新增')

    await wrapper.findAll('button').find((button) => button.text() === '回写为工作副本')!.trigger('click')
    await flushPromises()
    expect(clone).toHaveBeenCalledWith('case-7', 'fv-2')
    expect(wrapper.text()).toContain('v1 · confirmed')
  })

  it('does not save old case draft into the new case after a case switch', async () => {
    let resolveSave!: () => void
    const replace = vi.spyOn(apiV2, 'replaceFactsEntities').mockReturnValue(new Promise((resolve) => { resolveSave = () => resolve({}) }))
    vi.spyOn(apiV2, 'getFactsEntities').mockImplementation(async (caseId) => ({ caseId, items: [{ key: 'case', value: caseId }], entities: {} }))
    vi.spyOn(apiV2, 'getFactsHead').mockImplementation(async (caseId) => ({ caseId, confirmedFactsVersionId: null, updatedAt: null }))
    vi.spyOn(apiV2, 'listFactsVersions').mockResolvedValue({ items: [] })
    const wrapper = mount(CaseFactsPanel, { props: { caseId: 'case-a' } })
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text() === '编辑事实')!.trigger('click')
    await wrapper.find('input').setValue('case-a-draft')
    await wrapper.findAll('button').find((button) => button.text() === '保存草稿')!.trigger('click')
    await wrapper.setProps({ caseId: 'case-b' })
    await flushPromises()
    resolveSave()
    await flushPromises()

    expect(replace).toHaveBeenCalledWith('case-a', 'facts', expect.any(Array))
    expect(replace).not.toHaveBeenCalledWith('case-b', 'fact', expect.anything())
    expect(wrapper.text()).toContain('case-b')
  })

  it('does not apply a delayed old comparison after switching cases', async () => {
    let resolveDiff!: (value: { caseId: string; fromFactsVersionId: string; toFactsVersionId: string; sections: Record<string, never> }) => void
    const diff = vi.spyOn(apiV2, 'diffFactsVersion').mockReturnValue(new Promise((resolve) => { resolveDiff = resolve }))
    vi.spyOn(apiV2, 'getFactsEntities').mockImplementation(async (caseId) => ({ caseId, items: [], entities: {} }))
    vi.spyOn(apiV2, 'getFactsHead').mockImplementation(async (caseId) => ({ caseId, confirmedFactsVersionId: null, updatedAt: null }))
    vi.spyOn(apiV2, 'listFactsVersions').mockResolvedValue({ items: [
      { factsVersionId: 'fv-1', caseId: 'case-a', version: 1, status: 'draft', contentHash: 'h', createdAt: 't' },
      { factsVersionId: 'fv-2', caseId: 'case-a', version: 2, status: 'draft', contentHash: 'h', createdAt: 't' },
    ] })
    const wrapper = mount(CaseFactsPanel, { props: { caseId: 'case-a' } })
    await flushPromises()
    const selects = wrapper.findAll('select')
    await selects[0].setValue('fv-2')
    await selects[1].setValue('fv-1')
    await wrapper.findAll('button').find((button) => button.text() === '对比版本')!.trigger('click')
    await wrapper.setProps({ caseId: 'case-b' })
    await flushPromises()
    resolveDiff({ caseId: 'case-a', fromFactsVersionId: 'fv-1', toFactsVersionId: 'fv-2', sections: {} })
    await flushPromises()

    expect(diff).toHaveBeenCalledWith('case-a', 'fv-2', 'fv-1')
    expect(wrapper.text()).not.toContain('版本对比：')
  })

  it('does not let an earlier comparison overwrite a newer selected pair', async () => {
    let resolveFirst!: (value: { caseId: string; fromFactsVersionId: string; toFactsVersionId: string; sections: Record<string, never> }) => void
    let resolveSecond!: (value: { caseId: string; fromFactsVersionId: string; toFactsVersionId: string; sections: Record<string, never> }) => void
    const first = new Promise<{ caseId: string; fromFactsVersionId: string; toFactsVersionId: string; sections: Record<string, never> }>((resolve) => { resolveFirst = resolve })
    const second = new Promise<{ caseId: string; fromFactsVersionId: string; toFactsVersionId: string; sections: Record<string, never> }>((resolve) => { resolveSecond = resolve })
    const diff = vi.spyOn(apiV2, 'diffFactsVersion').mockReturnValueOnce(first).mockReturnValueOnce(second)
    vi.spyOn(apiV2, 'getFactsEntities').mockResolvedValue({ caseId: 'case-a', items: [], entities: {} })
    vi.spyOn(apiV2, 'getFactsHead').mockResolvedValue({ caseId: 'case-a', confirmedFactsVersionId: null, updatedAt: null })
    vi.spyOn(apiV2, 'listFactsVersions').mockResolvedValue({ items: [
      { factsVersionId: 'fv-1', caseId: 'case-a', version: 1, status: 'draft', contentHash: 'h', createdAt: 't' },
      { factsVersionId: 'fv-2', caseId: 'case-a', version: 2, status: 'draft', contentHash: 'h', createdAt: 't' },
    ] })
    const wrapper = mount(CaseFactsPanel, { props: { caseId: 'case-a' } })
    await flushPromises()
    const selects = wrapper.findAll('select')
    await selects[0].setValue('fv-2')
    await selects[1].setValue('fv-1')
    await wrapper.findAll('button').find((button) => button.text() === '对比版本')!.trigger('click')
    await selects[0].setValue('fv-1')
    await selects[1].setValue('fv-2')
    await wrapper.findAll('button').find((button) => button.text() === '对比版本')!.trigger('click')
    resolveFirst({ caseId: 'case-a', fromFactsVersionId: 'fv-2', toFactsVersionId: 'fv-1', sections: {} })
    await flushPromises()
    expect(wrapper.text()).not.toContain('版本对比：fv-1 → fv-2')
    resolveSecond({ caseId: 'case-a', fromFactsVersionId: 'fv-1', toFactsVersionId: 'fv-2', sections: {} })
    await flushPromises()
    expect(diff).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('版本对比：fv-1 → fv-2')
  })

  it('keeps confirm disabled while clone is pending', async () => {
    let resolveClone!: () => void
    const clone = vi.spyOn(apiV2, 'cloneFactsVersion').mockReturnValue(new Promise((resolve) => { resolveClone = () => resolve({}) }))
    vi.spyOn(apiV2, 'getFactsEntities').mockResolvedValue({ caseId: 'case-a', items: [{ key: 'x', value: '1' }], entities: {} })
    vi.spyOn(apiV2, 'getFactsHead').mockResolvedValue({ caseId: 'case-a', confirmedFactsVersionId: null, updatedAt: null })
    vi.spyOn(apiV2, 'listFactsVersions').mockResolvedValue({ items: [{ factsVersionId: 'fv-1', caseId: 'case-a', version: 1, status: 'draft', contentHash: 'h', createdAt: 't' }] })
    const wrapper = mount(CaseFactsPanel, { props: { caseId: 'case-a' } })
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text() === '回写为工作副本')!.trigger('click')
    await flushPromises()
    const confirmButton = wrapper.findAll('button').find((button) => button.text() === '确认事实')
    expect(confirmButton?.attributes('disabled')).toBeDefined()
    expect(clone).toHaveBeenCalledWith('case-a', 'fv-1')
    resolveClone()
    await flushPromises()
  })

  it('keeps a confirmed baseline visible while requiring confirmation for a divergent work copy', async () => {
    vi.spyOn(apiV2, 'getFactsEntities').mockResolvedValue({ caseId: 'case-a', items: [{ key: 'x', value: 'work' }], entities: {} })
    vi.spyOn(apiV2, 'getFactsHead').mockResolvedValue({ caseId: 'case-a', confirmedFactsVersionId: 'fv-1', updatedAt: null })
    vi.spyOn(apiV2, 'listFactsVersions').mockResolvedValue({ items: [{ factsVersionId: 'fv-1', caseId: 'case-a', version: 1, status: 'confirmed', contentHash: 'h', createdAt: 't' }] })
    vi.spyOn(apiV2, 'getFactsVersion').mockResolvedValue({
      factsVersionId: 'fv-1', caseId: 'case-a', version: 1, status: 'confirmed', contentHash: 'h', createdAt: 't',
      payload: { items: [{ key: 'x', value: 'baseline' }], entities: {} },
    })
    const wrapper = mount(CaseFactsPanel, { props: { caseId: 'case-a' } })
    await flushPromises()
    expect(wrapper.text()).toContain('已确认基线')
    expect(wrapper.text()).toContain('工作副本待建版确认')
    expect(wrapper.findAll('button').some((button) => button.text() === '确认事实')).toBe(true)
  })
})
