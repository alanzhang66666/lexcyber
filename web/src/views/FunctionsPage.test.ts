import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import { currentCaseId } from '../lib/current-case'
import FunctionsPage from './FunctionsPage.vue'

beforeEach(() => {
  sessionStorage.clear()
  currentCaseId.value = null
})

afterEach(() => {
  vi.restoreAllMocks()
})

async function mountFunctions() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/functions', component: FunctionsPage },
      { path: '/cases/:caseId/analysis', component: { template: '<div />' } },
      { path: '/cases', component: { template: '<div />' } },
      { path: '/compliance', component: { template: '<div />' } },
      { path: '/conviction', component: { template: '<div />' } },
      { path: '/reviews', component: { template: '<div />' } },
    ],
  })
  await router.push('/functions')
  await router.isReady()
  const wrapper = mount(FunctionsPage, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

describe('FunctionsPage', () => {
  it('selects a real T1 case for sentencing instead of lin-128', async () => {
    vi.spyOn(api, 'listCases').mockResolvedValue({
      items: [{ id: 't1-case-9', title: '交接样例案', createdAt: 't', updatedAt: 't' }],
      page: 0,
      size: 50,
      total: 1,
    })
    const wrapper = await mountFunctions()
    const sentencing = wrapper.findAll('a').find((item) => item.text().includes('量刑分析'))
    expect(sentencing?.attributes('href')).toBe('/cases/t1-case-9/analysis')
    expect(wrapper.html()).not.toContain('lin-128')
    expect(wrapper.text()).toContain('交接样例案')
    wrapper.unmount()
  })

  it('sends sentencing to the case list when no T1 case exists', async () => {
    vi.spyOn(api, 'listCases').mockResolvedValue({ items: [], page: 0, size: 50, total: 0 })
    const wrapper = await mountFunctions()
    const sentencing = wrapper.findAll('a').find((item) => item.text().includes('量刑分析'))
    expect(sentencing?.attributes('href')).toBe('/cases')
    wrapper.unmount()
  })
})
