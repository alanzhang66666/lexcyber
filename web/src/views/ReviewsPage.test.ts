import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import type { ReviewRecord } from '../api-types'
import ReviewsPage from './ReviewsPage.vue'

const realReview: ReviewRecord = {
  id: 'review-1', caseId: 't1-case-9', module: 'compliance', resultVersion: 3,
  moduleVersion: 2, status: 'pending', decision: 'none', archiveStatus: 'open',
}

function mountPage() {
  vi.spyOn(api, 'listReviews').mockResolvedValue({
    items: [realReview], page: 0, size: 20, total: 1,
  })
  return mount(ReviewsPage, {
    global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
  })
}

afterEach(() => vi.restoreAllMocks())

describe('ReviewsPage', () => {
  it('does not render the placeholder demo queue', async () => {
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.text()).not.toContain('示例队列')
    expect(wrapper.text()).not.toContain('林某')
    expect(wrapper.text()).not.toContain('赵某')
    wrapper.unmount()
  })

  it('shows source module, case, and result version for real reviews', async () => {
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.text()).toContain('合规筛查')
    expect(wrapper.text()).toContain('结果 v3')
    expect(wrapper.text()).toContain('模块 v2')
    expect(wrapper.text()).toContain('t1-case-9')
    wrapper.unmount()
  })

  it('flags archived reviews', async () => {
    vi.spyOn(api, 'listReviews').mockResolvedValue({
      items: [{ ...realReview, archiveStatus: 'archived' }], page: 0, size: 20, total: 1,
    })
    const wrapper = mount(ReviewsPage)
    await flushPromises()
    expect(wrapper.text()).toContain('已归档')
    wrapper.unmount()
  })
})
