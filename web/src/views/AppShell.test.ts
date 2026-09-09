import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import App from '../App.vue'
import { restoreSession } from '../lib/auth'
import router from '../router'

beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
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
})
