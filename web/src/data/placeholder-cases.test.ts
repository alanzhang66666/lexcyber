import { afterEach, describe, expect, it } from 'vitest'
import { PLACEHOLDER_CASES, findCase, lastCaseId, rememberCase, isPlaceholderCaseId, LAST_CASE_KEY } from './placeholder-cases'

afterEach(() => {
  sessionStorage.clear()
})

describe('placeholder cases', () => {
  it('covers the cross-border cybercrime workbench with three demo matters', () => {
    expect(PLACEHOLDER_CASES).toHaveLength(3)
    expect(PLACEHOLDER_CASES.map((item) => item.id)).toEqual(['lin-128', 'zhao-098', 'chen-076'])
    expect(PLACEHOLDER_CASES.some((item) => item.charge.includes('帮助信息网络'))).toBe(true)
    expect(findCase('missing').id).toBe('lin-128')
  })

  it('never treats placeholder ids as the current T1 case', () => {
    expect(isPlaceholderCaseId('lin-128')).toBe(true)
    expect(lastCaseId()).toBeNull()
    rememberCase('lin-128')
    expect(sessionStorage.getItem(LAST_CASE_KEY)).toBeNull()
    expect(lastCaseId()).toBeNull()
  })

  it('remembers only a real case id and clears a stale lin-128', () => {
    sessionStorage.setItem(LAST_CASE_KEY, 'lin-128')
    expect(lastCaseId()).toBeNull()
    expect(sessionStorage.getItem(LAST_CASE_KEY)).toBeNull()
    rememberCase('t1-case-22')
    expect(lastCaseId()).toBe('t1-case-22')
  })
})
