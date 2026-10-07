import type {
  ApiErrorPayload,
  AuthLogin,
  AuthRegister,
  ArchiveView,
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
  FactsDiffView,
  FactsEntityKind,
  ModuleStateUpdate,
  ModuleStateView,
  ModelAccessConfigUpdate,
  ModelAccessConfigView,
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
export const DOCX_CONTENT_TYPE = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'

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

function decodeFilename(value: string): string {
  const trimmed = value.trim().replace(/^"|"$/g, '')
  try {
    return decodeURIComponent(trimmed)
  } catch {
    return trimmed
  }
}

/** Keep a server-provided filename usable and within the download boundary. */
export function safeDownloadFilename(value: string | null | undefined, fallback = 'lexcyber-draft.docx'): string {
  const candidate = (value ?? '').replace(/[\\/\0-\x1f\x7f]/g, '_').trim()
  const base = candidate || fallback
  return base.toLowerCase().endsWith('.docx') ? base : `${base}.docx`
}

function contentDispositionFilename(header: string | null): string | null {
  if (!header) return null
  const encoded = header.match(/(?:^|;)\s*filename\*\s*=\s*(?:UTF-8''|utf-8'')([^;]+)/i)?.[1]
  if (encoded) return decodeFilename(encoded)
  const plain = header.match(/(?:^|;)\s*filename\s*=\s*([^;]+)/i)?.[1]
  return plain ? decodeFilename(plain) : null
}

export type BinaryDownload = { blob: Blob; filename: string }

async function requestBinary(path: string, init: RequestInit = {}): Promise<BinaryDownload> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)

  try {
    const response = await fetch(path, {
      ...init,
      headers: {
        Accept: DOCX_CONTENT_TYPE,
        ...authHeaders(),
        ...init.headers,
      },
      signal: controller.signal,
    })

    if (!response.ok) {
      const payload = await response.json().catch(() => null) as ApiErrorPayload | null
      const error = payload ?? {}
      throw new ApiError(error.message || error.detail || `请求失败（${response.status}）`, {
        status: response.status,
        code: error.code,
        traceId: error.traceId,
        retryable: error.retryable,
      })
    }

    const contentType = response.headers.get('Content-Type')?.split(';', 1)[0].trim().toLowerCase()
    if (contentType !== DOCX_CONTENT_TYPE) {
      throw new ApiError('服务器返回的文书格式无法识别。', {
        status: response.status,
        code: 'UNEXPECTED_CONTENT_TYPE',
      })
    }
    const blob = await response.blob()
    return {
      blob,
      filename: safeDownloadFilename(contentDispositionFilename(response.headers.get('Content-Disposition'))),
    }
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

  getModelAccessConfig() {
    return request<ModelAccessConfigView>('/v1/settings/model-access')
  },

  putModelAccessConfig(input: ModelAccessConfigUpdate) {
    return request<ModelAccessConfigView>('/v1/settings/model-access', {
      method: 'PUT',
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

  updateCaseAnalysisDate(caseId: string, asOfDate: string, expectedAsOfDate: string | null) {
    return request<CaseView>(`/v2/cases/${encodeURIComponent(caseId)}/analysis-date`, {
      method: 'PUT', body: JSON.stringify({ asOfDate, expectedAsOfDate }),
    })
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

/** /v2 生命周期端点（contracts/public-api-v2.yaml）。 */
export const apiV2 = {
  exportArtifactDocx(caseId: string, artifactVersionId: string) {
    return requestBinary(
      `/v2/cases/${encodeURIComponent(caseId)}/artifact-versions/${encodeURIComponent(artifactVersionId)}/export.docx`,
    )
  },

  getFactsEntities(caseId: string) {
    return request<Record<string, unknown>>(`/v2/cases/${encodeURIComponent(caseId)}/facts-entities`)
  },

  replaceFactsEntities(caseId: string, kind: FactsEntityKind, items: unknown[]) {
    return request<Record<string, unknown>>(
      `/v2/cases/${encodeURIComponent(caseId)}/facts-entities/${encodeURIComponent(kind)}`,
      { method: 'PUT', body: JSON.stringify({ items }) },
    )
  },

  createFactsVersion(caseId: string) {
    return request<Record<string, unknown>>(`/v2/cases/${encodeURIComponent(caseId)}/facts-versions`, {
      method: 'POST',
    })
  },

  diffFactsVersion(caseId: string, factsVersionId: string, againstFactsVersionId: string) {
    return request<FactsDiffView>(
      `/v2/cases/${encodeURIComponent(caseId)}/facts-versions/${encodeURIComponent(factsVersionId)}/diff?against=${encodeURIComponent(againstFactsVersionId)}`)
  },

  confirmFactsVersion(caseId: string, factsVersionId: string, expectedConfirmedId: string | null) {
    return request<Record<string, unknown>>(
      `/v2/cases/${encodeURIComponent(caseId)}/facts-versions/${encodeURIComponent(factsVersionId)}/confirm`,
      { method: 'POST', body: JSON.stringify({ expectedConfirmedFactsVersionId: expectedConfirmedId }) },
    )
  },

  listFactsVersions(caseId: string) {
    return request<{ items: Record<string, unknown>[] }>(
      `/v2/cases/${encodeURIComponent(caseId)}/facts-versions`)
  },

  getFactsVersion(caseId: string, factsVersionId: string) {
    return request<Record<string, unknown>>(
      `/v2/cases/${encodeURIComponent(caseId)}/facts-versions/${encodeURIComponent(factsVersionId)}`)
  },

  cloneFactsVersion(caseId: string, factsVersionId: string) {
    return request<Record<string, unknown>>(
      `/v2/cases/${encodeURIComponent(caseId)}/facts-versions/${encodeURIComponent(factsVersionId)}/clone`,
      { method: 'POST' })
  },

  getFactsHead(caseId: string) {
    return request<Record<string, unknown>>(`/v2/cases/${encodeURIComponent(caseId)}/facts-head`)
  },

  dispatchModuleExecution(caseId: string, module: string) {
    return request<Record<string, unknown>>(
      `/v2/cases/${encodeURIComponent(caseId)}/modules/${encodeURIComponent(module)}/executions`,
      { method: 'POST' })
  },

  dispatchDraftRender(caseId: string, docType: string) {
    return request<Record<string, unknown>>(
      `/v2/cases/${encodeURIComponent(caseId)}/drafts/render`,
      { method: 'POST', body: JSON.stringify({ docType }) })
  },

  getExecution(executionId: string) {
    return request<Record<string, unknown>>(`/v2/executions/${encodeURIComponent(executionId)}`)
  },

  getArtifactVersion(artifactVersionId: string) {
    return request<Record<string, unknown>>(`/v2/artifact-versions/${encodeURIComponent(artifactVersionId)}`)
  },

  getModuleHead(caseId: string, module: string) {
    return request<Record<string, unknown>>(
      `/v2/cases/${encodeURIComponent(caseId)}/modules/${encodeURIComponent(module)}`)
  },

  openReview(artifactVersionId: string, comment?: string) {
    return request<Record<string, unknown>>(
      `/v2/artifact-versions/${encodeURIComponent(artifactVersionId)}/reviews`,
      { method: 'POST', body: JSON.stringify({ comment: comment ?? null }) })
  },

  listReviews(artifactVersionId: string) {
    return request<{ items: Record<string, unknown>[] }>(
      `/v2/artifact-versions/${encodeURIComponent(artifactVersionId)}/reviews`)
  },

  listDraftStreams(caseId: string) {
    return request<{ items: Record<string, unknown>[] }>(
      `/v2/cases/${encodeURIComponent(caseId)}/drafts`)
  },

  getDraftHead(draftId: string) {
    return request<Record<string, unknown>>(`/v2/drafts/${encodeURIComponent(draftId)}`)
  },

  createArchive(caseId: string, archiveProfile = 'case.full.v1') {
    return request<Record<string, unknown>>(`/v2/cases/${encodeURIComponent(caseId)}/archives`, {
      method: 'POST', body: JSON.stringify({ archiveProfile }),
    })
  },

  getArchive(caseId: string, archiveId: string) {
    return request<ArchiveView>(
      `/v2/cases/${encodeURIComponent(caseId)}/archives/${encodeURIComponent(archiveId)}`)
  },
}
