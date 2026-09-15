import type {
  ApiErrorPayload,
  AuthLogin,
  AuthRegister,
  CaseCreate,
  CaseView,
  DocumentRole,
  DocumentView,
  DraftCreate,
  DraftList,
  DraftUpdate,
  DraftView,
  FactUpdate,
  FactView,
  ModuleStateUpdate,
  ModuleStateView,
  PageCase,
  PageDocument,
  ResultPayload,
  ReviewDecision,
  ReviewOpen,
  ReviewPage,
  ReviewRecord,
  SessionView,
  SourceSearchRequest,
  SourceSearchResponse,
  TaskCreate,
  TaskView,
} from './api-types'
import { getAccessToken } from './lib/session'

const REQUEST_TIMEOUT_MS = 12_000

export class ApiError extends Error {
  readonly status: number
  readonly code?: string
  readonly traceId?: string
  readonly retryable: boolean

  constructor(message: string, options: { status?: number; code?: string; traceId?: string; retryable?: boolean } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = options.status ?? 0
    this.code = options.code
    this.traceId = options.traceId
    this.retryable = options.retryable ?? false
  }
}

function authHeaders(): Record<string, string> {
  const token = getAccessToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)

  try {
    const response = await fetch(path, {
      ...init,
      headers: {
        Accept: 'application/json',
        ...(init.body && !(init.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}),
        ...authHeaders(),
        ...init.headers,
      },
      signal: controller.signal,
    })

    if (response.status === 204) return undefined as T

    const payload = await response.json().catch(() => null) as T | ApiErrorPayload | null

    if (!response.ok) {
      const error = (payload ?? {}) as ApiErrorPayload
      throw new ApiError(error.message || error.detail || `请求失败（${response.status}）`, {
        status: response.status,
        code: error.code,
        traceId: error.traceId,
        retryable: error.retryable,
      })
    }

    return payload as T
  } catch (error) {
    if (error instanceof ApiError) throw error
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError('请求超时，请检查服务状态后重试。', { code: 'CLIENT_TIMEOUT', retryable: true })
    }
    throw new ApiError('网络连接失败，请确认本地服务可用。', { code: 'NETWORK_ERROR', retryable: true })
  } finally {
    window.clearTimeout(timeout)
  }
}

function newIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

export const api = {
  register(input: AuthRegister) {
    return request<SessionView>('/v1/auth/register', { method: 'POST', body: JSON.stringify(input) })
  },

  login(input: AuthLogin) {
    return request<SessionView>('/v1/auth/login', { method: 'POST', body: JSON.stringify(input) })
  },

  logout() {
    return request<void>('/v1/auth/logout', { method: 'POST' })
  },

  getSession() {
    return request<SessionView>('/v1/auth/session')
  },

  createTask(input: TaskCreate) {
    return request<TaskView>('/v1/tasks', { method: 'POST', body: JSON.stringify(input) })
  },

  getTask(taskId: string) {
    return request<TaskView>(`/v1/tasks/${encodeURIComponent(taskId)}`)
  },

  retryTask(taskId: string) {
    return request<TaskView>(`/v1/tasks/${encodeURIComponent(taskId)}/retry`, { method: 'POST' })
  },

  getTaskResult(taskId: string) {
    return request<ResultPayload>(`/v1/tasks/${encodeURIComponent(taskId)}/result`)
  },

  listReviews(options: { status?: string; module?: string; archiveStatus?: string; page?: number; size?: number } = {}) {
    const params = new URLSearchParams()
    if (options.status) params.set('status', options.status)
    if (options.module) params.set('module', options.module)
    if (options.archiveStatus) params.set('archiveStatus', options.archiveStatus)
    params.set('page', String(options.page ?? 0))
    params.set('size', String(options.size ?? 20))
    return request<ReviewPage>(`/v1/reviews?${params.toString()}`)
  },

  getReview(reviewId: string) {
    return request<ReviewRecord>(`/v1/reviews/${encodeURIComponent(reviewId)}`)
  },

  decideReview(reviewId: string, decision: 'approve' | 'reject', input: ReviewDecision) {
    return request<ReviewRecord>(`/v1/reviews/${encodeURIComponent(reviewId)}/${decision}`, {
      method: 'POST',
      body: JSON.stringify(input),
    })
  },

  archiveReview(reviewId: string) {
    return request<ReviewRecord>(`/v1/reviews/${encodeURIComponent(reviewId)}/archive`, { method: 'POST' })
  },

  openCaseReview(caseId: string, input: ReviewOpen) {
    return request<ReviewRecord>(`/v1/cases/${encodeURIComponent(caseId)}/reviews`, {
      method: 'POST',
      body: JSON.stringify(input),
    })
  },

  getCaseModule(caseId: string, module: 'compliance' | 'conviction') {
    return request<ModuleStateView>(`/v1/cases/${encodeURIComponent(caseId)}/${module}`)
  },

  putCaseModule(caseId: string, module: 'compliance' | 'conviction', input: ModuleStateUpdate) {
    return request<ModuleStateView>(`/v1/cases/${encodeURIComponent(caseId)}/${module}`, {
      method: 'PUT',
      body: JSON.stringify(input),
    })
  },

  confirmCaseModule(caseId: string, module: 'compliance' | 'conviction') {
    return request<ModuleStateView>(
      `/v1/cases/${encodeURIComponent(caseId)}/${module}/confirm`,
      { method: 'POST' },
    )
  },

  getCaseFacts(caseId: string) {
    return request<FactView>(`/v1/cases/${encodeURIComponent(caseId)}/facts`)
  },

  putCaseFacts(caseId: string, input: FactUpdate) {
    return request<FactView>(`/v1/cases/${encodeURIComponent(caseId)}/facts`, {
      method: 'PUT',
      body: JSON.stringify(input),
    })
  },

  confirmCaseFacts(caseId: string) {
    return request<FactView>(`/v1/cases/${encodeURIComponent(caseId)}/facts/confirm`, { method: 'POST' })
  },

  createCaseDraft(caseId: string, input: DraftCreate) {
    return request<DraftView>(`/v1/cases/${encodeURIComponent(caseId)}/drafts`, {
      method: 'POST',
      body: JSON.stringify(input),
    })
  },

  listCaseDrafts(caseId: string) {
    return request<DraftList>(`/v1/cases/${encodeURIComponent(caseId)}/drafts`)
  },

  getCaseDraft(caseId: string, draftId: string) {
    return request<DraftView>(
      `/v1/cases/${encodeURIComponent(caseId)}/drafts/${encodeURIComponent(draftId)}`,
    )
  },

  putCaseDraft(caseId: string, draftId: string, input: DraftUpdate) {
    return request<DraftView>(
      `/v1/cases/${encodeURIComponent(caseId)}/drafts/${encodeURIComponent(draftId)}`,
      { method: 'PUT', body: JSON.stringify(input) },
    )
  },

  searchSources(input: SourceSearchRequest) {
    return request<SourceSearchResponse>('/v1/sources/search', {
      method: 'POST',
      body: JSON.stringify(input),
    })
  },

  createCase(input: CaseCreate) {
    return request<CaseView>('/v1/cases', { method: 'POST', body: JSON.stringify(input) })
  },

  listCases(options: { page?: number; size?: number } = {}) {
    const params = new URLSearchParams()
    params.set('page', String(options.page ?? 0))
    params.set('size', String(options.size ?? 20))
    return request<PageCase>(`/v1/cases?${params.toString()}`)
  },

  getCase(caseId: string) {
    return request<CaseView>(`/v1/cases/${encodeURIComponent(caseId)}`)
  },

  uploadDocument(caseId: string, file: File, role: DocumentRole, idempotencyKey?: string) {
    const form = new FormData()
    form.append('file', file)
    form.append('role', role)
    return request<DocumentView>(`/v1/cases/${encodeURIComponent(caseId)}/documents`, {
      method: 'POST',
      body: form,
      headers: { 'Idempotency-Key': idempotencyKey ?? newIdempotencyKey() },
    })
  },

  listDocuments(caseId: string, options: { role?: DocumentRole; page?: number; size?: number } = {}) {
    const params = new URLSearchParams()
    if (options.role) params.set('role', options.role)
    params.set('page', String(options.page ?? 0))
    params.set('size', String(options.size ?? 20))
    return request<PageDocument>(`/v1/cases/${encodeURIComponent(caseId)}/documents?${params.toString()}`)
  },

  getDocument(documentId: string) {
    return request<DocumentView>(`/v1/documents/${encodeURIComponent(documentId)}`)
  },
}
