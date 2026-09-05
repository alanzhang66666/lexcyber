import type {
  ApiErrorPayload,
  ResultPayload,
  ReviewDecision,
  ReviewPage,
  ReviewRecord,
  TaskCreate,
  TaskView,
} from './api-types'

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

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)

  try {
    const response = await fetch(path, {
      ...init,
      headers: {
        Accept: 'application/json',
        ...(init.body ? { 'Content-Type': 'application/json' } : {}),
        ...init.headers,
      },
      signal: controller.signal,
    })
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

export const api = {
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

  listReviews(options: { status?: string; page?: number; size?: number } = {}) {
    const params = new URLSearchParams()
    if (options.status) params.set('status', options.status)
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
}
