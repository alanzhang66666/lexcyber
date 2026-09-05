import { describe, expect, it } from 'vitest'
import { PLACEHOLDER_CASES, findCase } from './placeholder-cases'

describe('placeholder cases', () => {
  it('covers the cross-border cybercrime workbench with three demo matters', () => {
    expect(PLACEHOLDER_CASES).toHaveLength(3)
    expect(PLACEHOLDER_CASES.map((item) => item.id)).toEqual(['lin-128', 'zhao-098', 'chen-076'])
    expect(PLACEHOLDER_CASES.some((item) => item.charge.includes('帮助信息网络'))).toBe(true)
    expect(findCase('missing').id).toBe('lin-128')
  })
})
