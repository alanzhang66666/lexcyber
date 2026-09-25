import { computed, ref, type Ref } from 'vue'
import { ApiError, api } from '../api'
import type { CaseView, ModuleName, ModuleStateView } from '../api-types'
import { isPlaceholderCaseId } from '../data/placeholder-cases'
import { rememberT1Case } from '../lib/current-case'

/**
 * 案件级模块页共享逻辑：读案件 + 模块空壳状态 + 确认。
 * 合规 / 定罪两页复用；模块结果 404 时视为「尚未产生结果」，不当作错误。
 */
export function useCaseModule(caseId: Ref<string>, module: ModuleName) {
  const loading = ref(true)
  const error = ref('')
  const caseItem = ref<CaseView | null>(null)
  const moduleState = ref<ModuleStateView | null>(null)
  const confirming = ref(false)
  const confirmError = ref('')
  const isPlaceholder = computed(() => isPlaceholderCaseId(caseId.value))

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
      try {
        moduleState.value = await api.getCaseModule(caseId.value, module)
      } catch (caught) {
        if (caught instanceof ApiError && caught.status === 404) {
          moduleState.value = null
        } else {
          throw caught
        }
      }
    } catch (caught) {
      error.value = caught instanceof Error ? caught.message : '模块结果读取失败。'
    } finally {
      loading.value = false
    }
  }

  async function confirm() {
    confirming.value = true
    confirmError.value = ''
    try {
      moduleState.value = await api.confirmCaseModule(caseId.value, module)
    } catch (caught) {
      confirmError.value = caught instanceof Error ? caught.message : '确认失败。'
    } finally {
      confirming.value = false
    }
  }

  return { loading, error, caseItem, moduleState, confirming, confirmError, isPlaceholder, load, confirm }
}
