import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, api, apiV2 } from './api'

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  localStorage.clear()
})

function response(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('typed API client', () => {
  it('submits a task with the public contract shape', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response({ id: 'task-1', status: 'queued' }, 202))
    vi.stubGlobal('fetch', fetchMock)

    await api.createTask({ query: '核验材料', metadata: { source: 'test' } })

    expect(fetchMock).toHaveBeenCalledWith('/v1/tasks', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ query: '核验材料', metadata: { source: 'test' } }),
    }))
  })

  it('sends the user comment and immutable result version', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response({ id: 'review-1', status: 'approved' }))
    vi.stubGlobal('fetch', fetchMock)

    await api.decideReview('review-1', 'approve', { resultVersion: 3, comment: '证据与结果一致。' })

    expect(fetchMock).toHaveBeenCalledWith('/v1/reviews/review-1/approve', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ resultVersion: 3, comment: '证据与结果一致。' }),
    }))
  })

  it('registers against the Java identity contract', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response({
      token: 'tok-1', username: 'reviewer_01', displayName: '审核员',
    }, 201))
    vi.stubGlobal('fetch', fetchMock)

    await api.register({ username: 'reviewer_01', password: 'password1', displayName: '审核员' })

    expect(fetchMock).toHaveBeenCalledWith('/v1/auth/register', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ username: 'reviewer_01', password: 'password1', displayName: '审核员' }),
    }))
  })

  it('attaches a bearer session token to subsequent API calls', async () => {
    localStorage.setItem('lexcyber.session', JSON.stringify({
      token: 'sess-9', username: 'tester', displayName: '测试员',
    }))
    const fetchMock = vi.fn().mockResolvedValue(response({ id: 'task-1', status: 'queued' }, 202))
    vi.stubGlobal('fetch', fetchMock)

    await api.createTask({ query: '核验材料' })

    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect(init.headers).toEqual(expect.objectContaining({ Authorization: 'Bearer sess-9' }))
  })

  it('preserves conflict details for stale result versions', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({
      code: 'RESULT_VERSION_CONFLICT',
      message: 'stale result',
      traceId: 'trace-9',
      retryable: false,
    }, 409)))

    await expect(api.decideReview('review-1', 'reject', { resultVersion: 1 }))
      .rejects.toMatchObject({ status: 409, code: 'RESULT_VERSION_CONFLICT', traceId: 'trace-9' } satisfies Partial<ApiError>)
  })

  it('turns fetch failures into a retryable network error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))

    await expect(api.retryTask('task-1')).rejects.toMatchObject({
      code: 'NETWORK_ERROR',
      retryable: true,
    } satisfies Partial<ApiError>)
  })

  it('replaces fact entities through the /v2 lifecycle contract', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response({ items: [] }))
    vi.stubGlobal('fetch', fetchMock)

    await apiV2.replaceFactsEntities('case-7', 'fact', [{ key: '涉案金额', value: '1000' }])

    expect(fetchMock).toHaveBeenCalledWith('/v2/cases/case-7/facts-entities/fact',
      expect.objectContaining({
        method: 'PUT',
        body: JSON.stringify({ items: [{ key: '涉案金额', value: '1000' }] }),
      }))
  })

  it('sends the expected head for facts confirmation CAS', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response({ status: 'confirmed' }))
    vi.stubGlobal('fetch', fetchMock)

    await apiV2.confirmFactsVersion('case-7', 'fv-2', 'fv-1')

    expect(fetchMock).toHaveBeenCalledWith('/v2/cases/case-7/facts-versions/fv-2/confirm',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ expectedConfirmedFactsVersionId: 'fv-1' }),
      }))
  })

  it('sends null expected head for first-time confirmation', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response({ status: 'confirmed' }))
    vi.stubGlobal('fetch', fetchMock)

    await apiV2.confirmFactsVersion('case-7', 'fv-1', null)

    expect(fetchMock).toHaveBeenCalledWith('/v2/cases/case-7/facts-versions/fv-1/confirm',
      expect.objectContaining({
        body: JSON.stringify({ expectedConfirmedFactsVersionId: null }),
      }))
  })

  it('dispatches a module execution through /v2', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response({ executionId: 'ex-1' }, 202))
    vi.stubGlobal('fetch', fetchMock)

    await apiV2.dispatchModuleExecution('case-7', 'conviction')

    expect(fetchMock).toHaveBeenCalledWith('/v2/cases/case-7/modules/conviction/executions',
      expect.objectContaining({ method: 'POST' }))
  })

  it('dispatches a draft render with docType', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response({ executionId: 'ex-2' }, 202))
    vi.stubGlobal('fetch', fetchMock)

    await apiV2.dispatchDraftRender('case-7', 'indictment')

    expect(fetchMock).toHaveBeenCalledWith('/v2/cases/case-7/drafts/render',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ docType: 'indictment' }),
      }))
  })

  it('aborts a request that exceeds the client timeout', async () => {
    vi.useFakeTimers()
    vi.stubGlobal('fetch', vi.fn((_path: string, init: RequestInit) => new Promise((_resolve, reject) => {
      init.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
    })))
    const assertion = expect(api.getTask('task-1')).rejects.toMatchObject({
      code: 'CLIENT_TIMEOUT',
      retryable: true,
    } satisfies Partial<ApiError>)
    await vi.advanceTimersByTimeAsync(12_000)
    await assertion
  })
})
