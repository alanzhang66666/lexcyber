import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import { api } from '../api'
import type { CaseView } from '../api-types'
import CaseAnalysisDatePanel from './CaseAnalysisDatePanel.vue'

const original: CaseView = { id: 'case-1', title: '案件', asOfDate: null, createdAt: 't1', updatedAt: 't1' }
afterEach(() => vi.restoreAllMocks())

it('fills an existing undated case with an explicit date and expected-null CAS', async () => {
  const update = vi.spyOn(api, 'updateCaseAnalysisDate').mockResolvedValue({ ...original, asOfDate: '2024-03-01' })
  const panel = mount(CaseAnalysisDatePanel, { props: { caseItem: original } })
  expect(panel.get('button').attributes('disabled')).toBeDefined()
  await panel.get('input').setValue('2024-03-01')
  await panel.get('form').trigger('submit')
  await flushPromises()
  expect(update).toHaveBeenCalledWith('case-1', '2024-03-01', null)
  expect(panel.emitted('updated')?.[0]).toEqual([{ ...original, asOfDate: '2024-03-01' }])
})

it('preserves the server conflict and the current date', async () => {
  vi.spyOn(api, 'updateCaseAnalysisDate').mockRejectedValue(new Error('基准日期已变更，请刷新后再提交'))
  const panel = mount(CaseAnalysisDatePanel, { props: { caseItem: { ...original, asOfDate: '2024-03-01' } } })
  await panel.get('input').setValue('2024-04-01')
  await panel.get('form').trigger('submit')
  await flushPromises()
  expect(panel.get('[role="alert"]').text()).toContain('基准日期已变更')
  expect(panel.emitted('updated')).toBeUndefined()
})

it('ignores a date response belonging to the previous case', async () => {
  let finish!: (value: CaseView) => void
  vi.spyOn(api, 'updateCaseAnalysisDate').mockImplementation(() => new Promise(resolve => { finish = resolve }))
  const panel = mount(CaseAnalysisDatePanel, { props: { caseItem: original } })
  await panel.get('input').setValue('2024-03-01')
  await panel.get('form').trigger('submit')
  await panel.setProps({ caseItem: { ...original, id: 'case-2', title: '新案件', asOfDate: '2025-01-01' } })
  finish({ ...original, asOfDate: '2024-03-01' })
  await flushPromises()
  expect(panel.emitted('updated')).toBeUndefined()
  expect((panel.get('input').element as HTMLInputElement).value).toBe('2025-01-01')
})
