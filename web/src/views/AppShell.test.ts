import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import App from '../App.vue'
import { restoreSession } from '../lib/auth'
import { currentCaseId } from '../lib/current-case'
import router from '../router'

beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
  currentCaseId.value = null
  restoreSession()
  window.scrollTo = () => {}
})

afterEach(() => vi.restoreAllMocks())

function seedSession() {
  localStorage.setItem('lexcyber.session', JSON.stringify({
    token: 'test-token', username: 'tester', displayName: '测试员',
  }))
  restoreSession()
}

async function mountApp(path: string) {
  vi.spyOn(api, 'listReviews').mockResolvedValue({ items: [], page: 0, size: 20, total: 0 })
  vi.spyOn(api, 'listCases').mockResolvedValue({ items: [], page: 0, size: 50, total: 0 })
  vi.spyOn(api, 'getSession').mockResolvedValue({ username: 'tester', displayName: '测试员' })
  await router.push(path)
  await router.isReady()
  const wrapper = mount(App, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

describe('product shell', () => {
  it('shows the homepage first for anonymous visitors', async () => {
    const wrapper = await mountApp('/')
    expect(router.currentRoute.value.name).toBe('home')
    expect(wrapper.text()).toContain('Let Every Trace')
    expect(wrapper.text()).toContain('登录')
    expect(wrapper.text()).not.toContain('当前用户')
    wrapper.unmount()
  })

  it('opens the branded homepage instead of the task console', async () => {
    seedSession()
    const wrapper = await mountApp('/')
    expect(wrapper.text()).toContain('LexCyber')
    expect(wrapper.text()).toContain('网域衡鉴')
    expect(wrapper.text()).toContain('涉外互联网犯罪刑事合规与量刑辅助系统')
    expect(wrapper.text()).toContain('Let Every Trace')
    expect(wrapper.text()).toContain('穿透数据迷雾，锚定资金踪迹。')
    expect(wrapper.text()).toContain('规则可核，过程可溯。')
    expect(wrapper.text()).toContain('让智能辅助研判，让裁量归于人心。')
    expect(wrapper.text()).toContain('合规筛查')
    expect(wrapper.text()).toContain('定罪研判')
    expect(wrapper.text()).toContain('量刑分析')
    expect(wrapper.text()).toContain('复核归档')
    expect(wrapper.text()).toContain('立即体验')
    expect(wrapper.text()).not.toContain('开发中')
    wrapper.unmount()
  })

  it('keeps the live task intake behind the more-menu route', async () => {
    seedSession()
    const wrapper = await mountApp('/tasks')
    expect(wrapper.text()).toContain('提交分析请求')
    expect(wrapper.text()).toContain('提交任务')
    expect(wrapper.text()).not.toContain('POST /v1/tasks')
    wrapper.unmount()
  })

  it('keeps workspaces behind login for anonymous visitors', async () => {
    const wrapper = await mountApp('/cases')
    expect(router.currentRoute.value.name).toBe('login')
    expect(wrapper.text()).toContain('登录')
    expect(wrapper.text()).toContain('注册')
    wrapper.unmount()
  })

  it('points the home sentencing card at a real T1 case, not lin-128', async () => {
    seedSession()
    vi.spyOn(api, 'listReviews').mockResolvedValue({ items: [], page: 0, size: 20, total: 0 })
    vi.spyOn(api, 'getSession').mockResolvedValue({ username: 'tester', displayName: '测试员' })
    vi.spyOn(api, 'listCases').mockResolvedValue({
      items: [{ id: 't1-case-9', title: '交接样例案', createdAt: 't', updatedAt: 't' }],
      page: 0,
      size: 50,
      total: 1,
    })
    await router.push('/')
    await router.isReady()
    const wrapper = mount(App, { global: { plugins: [router] } })
    await flushPromises()
    const sentencing = wrapper.findAll('a').find((item) => item.text().includes('量刑分析'))
    expect(sentencing?.attributes('href')).toBe('/cases/t1-case-9/analysis')
    expect(wrapper.html()).not.toContain('lin-128')
    wrapper.unmount()
  })

  it('does not revive the leftover workspace dock even if layout=side is stored', async () => {
    seedSession()
    localStorage.setItem('lexcyber.ui-settings', JSON.stringify({
      theme: 'aurora', layout: 'side', density: 'comfortable',
    }))
    const wrapper = await mountApp('/cases')
    expect(wrapper.find('[aria-label="工作区侧栏"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('卷宗阅览')
    expect(wrapper.text()).not.toContain('工作区侧栏')
    wrapper.unmount()
  })

  it('opens 阅卷 from the case workspace instead of a global dock', async () => {
    seedSession()
    vi.spyOn(api, 'getCase').mockResolvedValue({
      id: 't1-case-9', title: '交接样例案', createdAt: 't', updatedAt: 't',
    })
    vi.spyOn(api, 'listDocuments').mockResolvedValue({ items: [], page: 0, size: 50, total: 0 })
    vi.spyOn(api, 'getCaseFacts').mockResolvedValue({
      caseId: 't1-case-9', schemaVersion: 'case.facts.v1', status: 'draft', items: [], updatedAt: 't', confirmedAt: null,
    })
    const wrapper = await mountApp('/cases/t1-case-9')
    expect(wrapper.find('[aria-label="工作区侧栏"]').exists()).toBe(false)
    const docket = wrapper.findAll('a').find((item) => item.text() === '打开阅卷')
    expect(docket?.attributes('href')).toBe('/cases/t1-case-9/docket')
    wrapper.unmount()
  })

  it('redirects /docket away from placeholder lin-128', async () => {
    seedSession()
    sessionStorage.setItem('lexcyber.last-case-id', 'lin-128')
    const wrapper = await mountApp('/docket')
    expect(router.currentRoute.value.path).toBe('/cases')
    expect(router.currentRoute.value.path).not.toContain('lin-128')
    wrapper.unmount()
  })

  it('keeps 功能中心 as a menu, not a standalone page', async () => {
    seedSession()
    const wrapper = await mountApp('/')
    currentCaseId.value = 't1-case-9'
    await flushPromises()
    const trigger = wrapper.findAll('button').find((item) => item.text() === '功能中心')
    expect(trigger).toBeTruthy()
    expect(document.querySelector('#functions-menu')).toBeNull()
    await trigger!.trigger('click')
    await flushPromises()
    const menu = document.querySelector('#functions-menu')
    expect(menu).toBeTruthy()
    expect(menu?.textContent).toContain('合规筛查')
    expect(menu?.textContent).toContain('定罪研判')
    expect(menu?.textContent).toContain('量刑分析')
    expect(menu?.textContent).toContain('复核归档')
    const sentencing = menu?.querySelectorAll('a')
    const sentencingLink = Array.from(sentencing ?? []).find((item) => item.textContent?.includes('量刑分析'))
    expect(sentencingLink?.getAttribute('href')).toBe('/cases/t1-case-9/analysis')
    expect(wrapper.html()).not.toContain('lin-128')
    const casesLink = wrapper.findAll('a').find((item) => item.text() === '案件中心')
    expect(casesLink?.attributes('href')).toBe('/cases')
    wrapper.unmount()
  })

  it('sends the sentencing menu item to the case list when no T1 case exists', async () => {
    seedSession()
    vi.spyOn(api, 'listCases').mockResolvedValue({ items: [], page: 0, size: 50, total: 0 })
    const wrapper = await mountApp('/')
    const trigger = wrapper.findAll('button').find((item) => item.text() === '功能中心')
    await trigger!.trigger('click')
    await flushPromises()
    const sentencingLink = Array.from(document.querySelectorAll('#functions-menu a'))
      .find((item) => item.textContent?.includes('量刑分析'))
    expect(sentencingLink?.getAttribute('href')).toBe('/cases')
    wrapper.unmount()
  })

  it('redirects the old /functions page to home', async () => {
    const wrapper = await mountApp('/functions')
    expect(router.currentRoute.value.path).toBe('/')
    expect(wrapper.find('h1').text()).not.toBe('功能中心')
    wrapper.unmount()
  })

  it('redirects /analysis to the remembered T1 case', async () => {
    seedSession()
    sessionStorage.setItem('lexcyber.last-case-id', 't1-case-9')
    currentCaseId.value = 't1-case-9'
    vi.spyOn(api, 'getCase').mockResolvedValue({
      id: 't1-case-9', title: '交接样例案', createdAt: 't', updatedAt: 't',
    })
    const wrapper = await mountApp('/analysis')
    expect(router.currentRoute.value.path).toBe('/cases/t1-case-9/analysis')
    expect(wrapper.text()).toContain('尚未运行量刑分析')
    expect(wrapper.text()).not.toContain('林某')
    wrapper.unmount()
  })
})
