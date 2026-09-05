import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, api } from '../api'
import type { ReviewRecord, TaskView } from '../api-types'
import ReviewDetailPage from './ReviewDetailPage.vue'

const review: ReviewRecord = {
  id: 'review-1', taskId: 'task-1', resultVersion: 4, status: 'pending', decision: 'none',
}
const task: TaskView = {
  id: 'task-1', requestId: 'request-1', executionId: 'execution-1',
  status: 'waiting_review', currentStage: 'review', createdAt: '2026-09-05T00:00:00Z',
  result: { resultId: 'result-1', version: 4, type: 'analysis' },
}

function mountPage(resultVersion = 4) {
  vi.spyOn(api, 'getReview').mockResolvedValue({ ...review })
  vi.spyOn(api, 'getTask').mockResolvedValue({ ...task })
  vi.spyOn(api, 'getTaskResult').mockResolvedValue({
    resultId: 'result-1', version: resultVersion, type: 'analysis', contentHash: 'sha256:abc', content: { ok: true },
  })
  return mount(ReviewDetailPage, {
    props: { reviewId: 'review-1' },
    global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
  })
}

afterEach(() => vi.restoreAllMocks())

describe('ReviewDetailPage', () => {
  it.each([
    ['approve', '批准结果'],
    ['reject', '拒绝结果'],
  ] as const)('submits a written %s decision for the loaded version', async (decision, label) => {
    const decideReview = vi.spyOn(api, 'decideReview').mockResolvedValue({
      ...review,
      status: decision === 'approve' ? 'approved' : 'rejected',
      decision,
      comment: '已逐项核验证据。',
    })
    const wrapper = mountPage()
    await flushPromises()
    await wrapper.get('textarea').setValue('已逐项核验证据。')
    const button = wrapper.findAll('button').find((item) => item.text().includes(label))
    expect(button).toBeDefined()
    await button!.trigger('click')
    await flushPromises()

    expect(decideReview).toHaveBeenCalledWith('review-1', decision, {
      resultVersion: 4,
      comment: '已逐项核验证据。',
    })
  })

  it('blocks empty review comments', async () => {
    const decideReview = vi.spyOn(api, 'decideReview')
    const wrapper = mountPage()
    await flushPromises()
    const approve = wrapper.findAll('button').find((item) => item.text().includes('批准结果'))
    expect(approve?.attributes('disabled')).toBeDefined()
    expect(decideReview).not.toHaveBeenCalled()
  })

  it('explains a stale result-version conflict', async () => {
    vi.spyOn(api, 'decideReview').mockRejectedValue(new ApiError('conflict', { status: 409 }))
    const wrapper = mountPage()
    await flushPromises()
    await wrapper.get('textarea').setValue('按当前材料拒绝。')
    const reject = wrapper.findAll('button').find((item) => item.text().includes('拒绝结果'))
    await reject!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('结果版本或复核状态已经变化')
  })

  it('does not offer a decision when the loaded result version differs', async () => {
    const wrapper = mountPage(5)
    await flushPromises()
    expect(wrapper.text()).toContain('与待复核的 v4 不一致')
    expect(wrapper.text()).not.toContain('批准结果')
    expect(wrapper.text()).not.toContain('拒绝结果')
  })
})
