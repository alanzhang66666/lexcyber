import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, api, apiV2, safeDownloadFilename } from './api'

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

    await apiV2.replaceFactsEntities('case-7', 'facts', [{ key: '涉案金额', value: '1000' }])

    expect(fetchMock).toHaveBeenCalledWith('/v2/cases/case-7/facts-entities/facts',
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

  it('uses the facts version diff contract with an against query', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response({
      caseId: 'case-7', fromFactsVersionId: 'fv-1', toFactsVersionId: 'fv-2', sections: {},
    }))
    vi.stubGlobal('fetch', fetchMock)

    await apiV2.diffFactsVersion('case-7', 'fv-2', 'fv-1')

    expect(fetchMock).toHaveBeenCalledWith('/v2/cases/case-7/facts-versions/fv-2/diff?against=fv-1', expect.anything())
  })

  it('creates and reads a case archive through the v2 contract', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ archiveId: 'arc-1' }, 201))
      .mockResolvedValueOnce(response({ archiveId: 'arc-1', manifestHash: 'sha256:x' }))
    vi.stubGlobal('fetch', fetchMock)

    await apiV2.createArchive('case-7')
    await apiV2.getArchive('case-7', 'arc-1')

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/v2/cases/case-7/archives', expect.objectContaining({
      method: 'POST', body: JSON.stringify({ archiveProfile: 'case.full.v1' }),
    }))
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/v2/cases/case-7/archives/arc-1', expect.anything())
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

  it('downloads an immutable DOCX artifact with auth and RFC5987 filename', async () => {
    localStorage.setItem('lexcyber.session', JSON.stringify({ token: 'sess-docx', username: 'tester', displayName: '测试员' }))
    const fetchMock = vi.fn().mockResolvedValue(new Response(new Uint8Array([80, 75, 3, 4]), {
      status: 200,
      headers: {
        'Content-Type': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'Content-Disposition': "attachment; filename*=UTF-8''%E5%AE%A1%E6%9F%A5%E6%8A%A5%E5%91%8A.docx",
      },
    }))
    vi.stubGlobal('fetch', fetchMock)

    const result = await apiV2.exportArtifactDocx('case/7', 'artifact-9')

    expect(result.filename).toBe('审查报告.docx')
    expect(result.blob.type).toBe('application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    expect(fetchMock).toHaveBeenCalledWith(
      '/v2/cases/case%2F7/artifact-versions/artifact-9/export.docx',
      expect.objectContaining({ headers: expect.objectContaining({
        Accept: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        Authorization: 'Bearer sess-docx',
      }) }),
    )
  })

  it('preserves structured JSON errors from DOCX export', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({
      code: 'DRAFT_EXPORT_UNAVAILABLE', message: '正文尚未具备导出条件。', traceId: 'trace-docx',
    }, 409)))

    await expect(apiV2.exportArtifactDocx('case-7', 'artifact-9')).rejects.toMatchObject({
      status: 409, code: 'DRAFT_EXPORT_UNAVAILABLE', traceId: 'trace-docx',
    } satisfies Partial<ApiError>)
  })

  it('rejects a successful response with the wrong media type', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('not a docx', {
      status: 200, headers: { 'Content-Type': 'text/plain' },
    })))

    await expect(apiV2.exportArtifactDocx('case-7', 'artifact-9')).rejects.toMatchObject({
      code: 'UNEXPECTED_CONTENT_TYPE', status: 200,
    } satisfies Partial<ApiError>)
  })

  it('sanitizes plain filenames, path separators, and control characters', () => {
    expect(safeDownloadFilename('报告/../\u0000草稿')).toBe('报告_..__草稿.docx')
    expect(safeDownloadFilename('报告.docx')).toBe('报告.docx')
    expect(safeDownloadFilename('')).toBe('lexcyber-draft.docx')
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
