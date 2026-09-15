import { describe, expect, it } from 'vitest'
import { CORE_MODULES, modulePath } from './modules'

const sentencing = CORE_MODULES.find((item) => item.key === 'sentencing')!

describe('modulePath', () => {
  it('substitutes a real T1 case id on sentencing', () => {
    expect(modulePath(sentencing, 't1-case-22')).toBe('/cases/t1-case-22/analysis')
  })

  it('sends sentencing to the case list when no real case is selected', () => {
    expect(modulePath(sentencing, null)).toBe('/cases')
    expect(modulePath(sentencing, undefined)).toBe('/cases')
    expect(modulePath(sentencing, 'lin-128')).toBe('/cases')
    expect(modulePath(sentencing, 'zhao-098')).toBe('/cases')
  })

  it('leaves modules without a case placeholder unchanged', () => {
    const review = CORE_MODULES.find((item) => item.key === 'review')!
    expect(modulePath(review, 'lin-128')).toBe('/reviews')
    expect(modulePath(review, null)).toBe('/reviews')
  })
})
