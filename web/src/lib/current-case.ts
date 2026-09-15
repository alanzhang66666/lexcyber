import { ref } from 'vue'
import { api } from '../api'
import type { CaseView } from '../api-types'
import { isPlaceholderCaseId, lastCaseId, rememberCase } from '../data/placeholder-cases'

export const currentCaseId = ref<string | null>(lastCaseId())

export function syncCurrentCaseFromStorage() {
  currentCaseId.value = lastCaseId()
  return currentCaseId.value
}

export function rememberT1Case(id: string) {
  rememberCase(id)
  return syncCurrentCaseFromStorage()
}

export function formalCasePath(kind: 'docket' | 'analysis', caseId: string | null | undefined): string {
  if (!caseId || isPlaceholderCaseId(caseId)) return '/cases'
  return `/cases/${caseId}/${kind}`
}

export async function loadT1Cases(): Promise<CaseView[]> {
  const page = await api.listCases({ page: 0, size: 50 })
  const items = page.items.filter((item) => item.id && !isPlaceholderCaseId(item.id))
  if (!lastCaseId() && items[0]) rememberT1Case(items[0].id)
  else syncCurrentCaseFromStorage()
  return items
}

/** Remembered T1 id, or the first owner-scoped case from the list API. Never lin-128. */
export async function resolveT1CaseId(): Promise<string | null> {
  const remembered = lastCaseId()
  if (remembered) {
    currentCaseId.value = remembered
    return remembered
  }
  try {
    await loadT1Cases()
  } catch {
    currentCaseId.value = null
  }
  return currentCaseId.value
}
