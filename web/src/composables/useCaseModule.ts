import { computed, onScopeDispose, ref, type Ref } from 'vue'
import { api, apiV2 } from '../api'
import type { CaseView, ModuleApplicability, ModuleDispatchOptions, ModuleName, ModuleStateView } from '../api-types'
import { isPlaceholderCaseId } from '../data/placeholder-cases'
import { rememberT1Case } from '../lib/current-case'

const POLL_MS = 1500
const POLL_LIMIT = 80

/**
 * 案件级模块页共享逻辑（/v2 生命周期语义）。
 * 读案件 + 模块头 + 最新工件版本 payload，映射为页面既有的 ModuleStateView 展示形状。
 * confirm 对应 v2 人工复核入口（对最新工件版本开复核单）；dispatch 触发模块执行后轮询。
 */
export function useCaseModule(caseId: Ref<string>, module: ModuleName) {
  const loading = ref(true)
  const error = ref('')
  const caseItem = ref<CaseView | null>(null)
  const moduleState = ref<ModuleStateView | null>(null)
  const confirming = ref(false)
  const confirmError = ref('')
  const dispatching = ref(false)
  const dispatchError = ref('')
  const isPlaceholder = computed(() => isPlaceholderCaseId(caseId.value))
  let pollTimer: number | undefined

  function stopPolling() {
    if (pollTimer !== undefined) {
      window.clearInterval(pollTimer)
      pollTimer = undefined
    }
  }
  onScopeDispose(stopPolling)

  function toView(head: Record<string, unknown>, artifact: Record<string, unknown> | null): ModuleStateView {
    const payload = (artifact?.payload ?? {}) as Record<string, unknown>
    const outcome = String(artifact?.outcomeStatus ?? payload.status ?? '')
    const applicability: ModuleApplicability =
      payload.status === 'not_applicable' ? 'not_applicable'
        : outcome === 'blocked' ? 'limited_context'
          : artifact ? 'applicable' : 'unknown'
    return {
      caseId: caseId.value,
      module,
      schemaVersion: 'case.module.v1',
      applicability,
      status: head.effectivelyConfirmed === true ? 'confirmed' : 'draft',
      version: Number(artifact?.version ?? 0),
      content: payload,
      sourceVersion: (artifact?.schemaVersion ?? null) as string | null,
      factsStale: head.stale === true,
      updatedAt: String(head.updatedAt ?? artifact?.createdAt ?? ''),
      confirmedAt: head.effectivelyConfirmed === true ? (head.updatedAt as string | null) : null,
    }
  }

  async function load() {
    loading.value = true
    error.value = ''
    caseItem.value = null
    moduleState.value = null
    if (!caseId.value || isPlaceholder.value) {
      loading.value = false
      return
    }
    try {
      caseItem.value = await api.getCase(caseId.value)
      rememberT1Case(caseItem.value.id)
      const head = await apiV2.getModuleHead(caseId.value, module)
      const latestId = head.latestVersionId as string | null
      if (!latestId) {
        moduleState.value = null
        return
      }
      const artifact = await apiV2.getArtifactVersion(latestId)
      moduleState.value = toView(head, artifact)
    } catch (caught) {
      error.value = caught instanceof Error ? caught.message : '模块结果读取失败。'
    } finally {
      loading.value = false
    }
  }

  async function dispatch(options?: ModuleDispatchOptions | Event) {
    dispatching.value = true
    dispatchError.value = ''
    try {
      const dispatchOptions = options instanceof Event ? undefined : options
      const created = await apiV2.dispatchModuleExecution(caseId.value, module, dispatchOptions)
      const executionId = String(created.executionId ?? '')
      if (!executionId) throw new Error('派发响应缺少 executionId')
      await pollExecution(executionId)
      await load()
    } catch (caught) {
      dispatchError.value = caught instanceof Error ? caught.message : '模块执行失败。'
    } finally {
      dispatching.value = false
    }
  }

  async function pollExecution(executionId: string) {
    for (let attempt = 0; attempt < POLL_LIMIT; attempt += 1) {
      const exec = await apiV2.getExecution(executionId)
      const state = String(exec.state ?? '')
      if (state === 'completed') return
      if (state === 'failed') throw new Error('模块执行失败，请稍后重试。')
      await new Promise((resolve) => { pollTimer = window.setTimeout(resolve, POLL_MS) })
    }
    throw new Error('模块执行超时，请稍后在任务中心查看。')
  }

  async function confirm() {
    confirming.value = true
    confirmError.value = ''
    try {
      const head = await apiV2.getModuleHead(caseId.value, module)
      const latestId = head.latestVersionId as string | null
      if (!latestId) throw new Error('尚无工件版本可复核')
      await apiV2.openReview(latestId)
      await load()
    } catch (caught) {
      confirmError.value = caught instanceof Error ? caught.message : '提交复核失败。'
    } finally {
      confirming.value = false
    }
  }

  return { loading, error, caseItem, moduleState, confirming, confirmError, dispatching, dispatchError, isPlaceholder, load, dispatch, confirm }
}
