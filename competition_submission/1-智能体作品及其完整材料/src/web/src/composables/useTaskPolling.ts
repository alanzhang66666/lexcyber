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

  function stop() {
    if (timer !== undefined) {
      window.clearInterval(timer)
      timer = undefined
    }
  }

  async function loadResult() {
    const current = task.value
    if (!current?.result) return

    resultLoading.value = true
    try {
      result.value = await api.getTaskResult(current.id)
    } catch (caught) {
      error.value = caught instanceof Error ? caught.message : '结果读取失败。'
    } finally {
      resultLoading.value = false
    }
  }

  async function refresh() {
    const id = taskId()
    if (!id) return

    loading.value = !task.value
    try {
      task.value = await api.getTask(id)
      error.value = ''
      if (task.value.result && ['completed', 'waiting_review'].includes(task.value.status)) {
        await loadResult()
      }
      if (isTaskSettled(task.value.status)) stop()
    } catch (caught) {
      error.value = caught instanceof Error ? caught.message : '任务读取失败。'
    } finally {
      loading.value = false
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
