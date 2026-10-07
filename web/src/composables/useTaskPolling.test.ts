import { defineComponent, h, onMounted, ref } from 'vue'
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
    expect(state.loading.value).toBe(false)
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

  it('ignores a prior route response after polling switches task ids', async () => {
    let resolveOld!: (task: TaskView) => void
    const oldResponse = new Promise<TaskView>((resolve) => { resolveOld = resolve })
    const newer: TaskView = { ...running, id: 'task-2' }
    const getTask = vi.spyOn(api, 'getTask')
      .mockReturnValueOnce(oldResponse)
      .mockResolvedValueOnce(newer)
    const currentId = ref('task-1')
    let state!: ReturnType<typeof useTaskPolling>
    const Host = defineComponent({
      setup() {
        state = useTaskPolling(() => currentId.value, 100)
        onMounted(state.start)
        return () => h('div')
      },
    })
    const wrapper = mount(Host)
    await flushPromises()
    currentId.value = 'task-2'
    state.start()
    await flushPromises()
    expect(state.task.value?.id).toBe('task-2')

    resolveOld({ ...running, id: 'task-1' })
    await flushPromises()
    expect(state.task.value?.id).toBe('task-2')
    expect(getTask).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('does not let a delayed old result overwrite or stop the new route poll', async () => {
    let resolveOldResult!: (result: ReturnType<typeof api.getTaskResult> extends Promise<infer T> ? T : never) => void
    const oldResult = new Promise<Awaited<ReturnType<typeof api.getTaskResult>>>((resolve) => { resolveOldResult = resolve })
    const oldTask: TaskView = { ...completed, id: 'task-old' }
    const newTask: TaskView = { ...running, id: 'task-new' }
    const getTask = vi.spyOn(api, 'getTask')
      .mockResolvedValueOnce(oldTask)
      .mockResolvedValueOnce(newTask)
      .mockResolvedValue(newTask)
    vi.spyOn(api, 'getTaskResult').mockReturnValueOnce(oldResult)
    const currentId = ref('task-old')
    let state!: ReturnType<typeof useTaskPolling>
    const Host = defineComponent({
      setup() {
        state = useTaskPolling(() => currentId.value, 100)
        onMounted(state.start)
        return () => h('div')
      },
    })
    const wrapper = mount(Host)
    await flushPromises()
    currentId.value = 'task-new'
    state.start()
    await flushPromises()
    expect(state.task.value?.id).toBe('task-new')

    resolveOldResult({ resultId: 'old-result', version: 1, type: 'analysis', contentHash: 'old', content: { old: true } })
    await flushPromises()
    expect(state.result.value).toBeNull()

    await vi.advanceTimersByTimeAsync(100)
    await flushPromises()
    expect(getTask).toHaveBeenCalledTimes(3)
    expect(state.task.value?.id).toBe('task-new')
    wrapper.unmount()
  })
})
