import { defineComponent, h, onMounted } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import type { TaskView } from '../api-types'
import { useTaskPolling } from './useTaskPolling'

const running: TaskView = {
  id: 'task-1', requestId: 'request-1', executionId: 'execution-1',
  status: 'running', currentStage: 'dispatch', createdAt: '2026-09-05T00:00:00Z',
}
const completed: TaskView = {
  ...running,
  status: 'completed',
  currentStage: 'complete',
  result: { resultId: 'result-1', version: 2, type: 'analysis' },
}

beforeEach(() => vi.useFakeTimers())
afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('useTaskPolling', () => {
  it('loads the result and stops polling at a terminal status', async () => {
    const getTask = vi.spyOn(api, 'getTask')
      .mockResolvedValueOnce(running)
      .mockResolvedValueOnce(completed)
    vi.spyOn(api, 'getTaskResult').mockResolvedValue({
      resultId: 'result-1', version: 2, type: 'analysis', contentHash: 'sha256:abc', content: { ok: true },
    })
    let state!: ReturnType<typeof useTaskPolling>
    const Host = defineComponent({
      setup() {
        state = useTaskPolling(() => 'task-1', 100)
        onMounted(state.start)
        return () => h('div')
      },
    })
    const wrapper = mount(Host)
    await flushPromises()
    expect(state.task.value?.status).toBe('running')

    await vi.advanceTimersByTimeAsync(100)
    await flushPromises()
    expect(state.task.value?.status).toBe('completed')
    expect(state.result.value?.version).toBe(2)

    await vi.advanceTimersByTimeAsync(500)
    expect(getTask).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('cleans up its timer when the component unmounts', async () => {
    const getTask = vi.spyOn(api, 'getTask').mockResolvedValue(running)
    let state!: ReturnType<typeof useTaskPolling>
    const Host = defineComponent({
      setup() {
        state = useTaskPolling(() => 'task-1', 100)
        onMounted(state.start)
        return () => h('div')
      },
    })
    const wrapper = mount(Host)
    await flushPromises()
    wrapper.unmount()
    await vi.advanceTimersByTimeAsync(500)
    expect(getTask).toHaveBeenCalledTimes(1)
  })

  it('exposes polling failures for an actionable retry', async () => {
    vi.spyOn(api, 'getTask').mockRejectedValue(new Error('服务暂不可用'))
    let state!: ReturnType<typeof useTaskPolling>
    const Host = defineComponent({
      setup() {
        state = useTaskPolling(() => 'task-1', 100)
        onMounted(state.start)
        return () => h('div')
      },
    })
    const wrapper = mount(Host)
    await flushPromises()
    expect(state.error.value).toBe('服务暂不可用')
    wrapper.unmount()
  })
})
