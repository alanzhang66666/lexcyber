import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import { LAST_CASE_KEY } from '../data/placeholder-cases'
import {
  currentCaseId,
  formalCasePath,
  loadT1Cases,
  rememberT1Case,
  resolveT1CaseId,
  syncCurrentCaseFromStorage,
} from './current-case'

beforeEach(() => {
  sessionStorage.clear()
  currentCaseId.value = null
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('current T1 case', () => {
  it('resolves the remembered real case without calling the list API', async () => {
    const listCases = vi.spyOn(api, 'listCases')
    rememberT1Case('t1-case-22')
    await expect(resolveT1CaseId()).resolves.toBe('t1-case-22')
    expect(listCases).not.toHaveBeenCalled()
    expect(currentCaseId.value).toBe('t1-case-22')
  })

  it('picks the first owner-scoped case when nothing is remembered', async () => {
    vi.spyOn(api, 'listCases').mockResolvedValue({
      items: [
        { id: 't1-case-9', title: '交接样例', createdAt: 't', updatedAt: 't' },
        { id: 't1-case-8', title: '另一案', createdAt: 't', updatedAt: 't' },
      ],
      page: 0,
      size: 50,
      total: 2,
    })
    await expect(resolveT1CaseId()).resolves.toBe('t1-case-9')
    expect(sessionStorage.getItem(LAST_CASE_KEY)).toBe('t1-case-9')
  })

  it('ignores placeholder ids from the list and from storage', async () => {
    sessionStorage.setItem(LAST_CASE_KEY, 'lin-128')
    syncCurrentCaseFromStorage()
    vi.spyOn(api, 'listCases').mockResolvedValue({
      items: [{ id: 'lin-128', title: '不应选用', createdAt: 't', updatedAt: 't' }],
      page: 0,
      size: 50,
      total: 1,
    })
    await expect(loadT1Cases()).resolves.toEqual([])
    expect(currentCaseId.value).toBeNull()
    expect(formalCasePath('docket', 'lin-128')).toBe('/cases')
    expect(formalCasePath('analysis', 't1-case-9')).toBe('/cases/t1-case-9/analysis')
  })

  it('returns null when the list API is unavailable', async () => {
    vi.spyOn(api, 'listCases').mockRejectedValue(new Error('unauthorized'))
    await expect(resolveT1CaseId()).resolves.toBeNull()
    expect(currentCaseId.value).toBeNull()
  })
})
