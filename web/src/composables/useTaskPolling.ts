import { onScopeDispose, ref } from 'vue'
import { api } from '../api'
import type { ResultPayload, TaskStatus, TaskView } from '../api-types'

const STOP_STATUSES: TaskStatus[] = ['completed', 'waiting_review', 'failed', 'timed_out', 'rejected']

export function isTaskSettled(status: TaskStatus) {
  return STOP_STATUSES.includes(status)
}

export function useTaskPolling(taskId: () => string, intervalMs = 1500) {
  const task = ref<TaskView | null>(null)
  const result = ref<ResultPayload | null>(null)
  const loading = ref(false)
  const resultLoading = ref(false)
  const error = ref('')
  let timer: number | undefined
  let requestGeneration = 0

  function stop(invalidate = true) {
    if (invalidate) requestGeneration += 1
    if (timer !== undefined) {
      window.clearInterval(timer)
      timer = undefined
    }
  }

  async function loadResult(current: TaskView, generation: number) {
    if (!current?.result) return

    resultLoading.value = true
    try {
      const loaded = await api.getTaskResult(current.id)
      if (generation === requestGeneration && taskId() === current.id) {
        result.value = loaded
      }
    } catch (caught) {
      if (generation === requestGeneration && taskId() === current.id) {
        error.value = caught instanceof Error ? caught.message : '结果读取失败。'
      }
    } finally {
      if (generation === requestGeneration) resultLoading.value = false
    }
  }

  async function refresh() {
    const id = taskId()
    if (!id) return
    const generation = ++requestGeneration

    loading.value = !task.value || task.value.id !== id
    try {
      const loaded = await api.getTask(id)
      if (generation !== requestGeneration || taskId() !== id) return
      task.value = loaded
      error.value = ''
      if (loaded.result && ['completed', 'waiting_review'].includes(loaded.status)) {
        await loadResult(loaded, generation)
      }
      if (generation !== requestGeneration || taskId() !== id) return
      if (isTaskSettled(loaded.status)) stop(false)
    } catch (caught) {
      if (generation === requestGeneration && taskId() === id) {
        error.value = caught instanceof Error ? caught.message : '任务读取失败。'
      }
    } finally {
      if (generation === requestGeneration) loading.value = false
    }
  }

  function start() {
    stop()
    void refresh()
    timer = window.setInterval(() => void refresh(), intervalMs)
  }

  onScopeDispose(stop)

  return { task, result, loading, resultLoading, error, refresh, start, stop }
}
