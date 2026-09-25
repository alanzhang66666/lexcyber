import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api'
import { isAuthenticated, loginAccount, logout, registerAccount, restoreSession, safeRedirect } from './auth'

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
  restoreSession()
})

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('java identity auth gate', () => {
  it('registers through the identity API and keeps a session token', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({
      token: 'tok-1',
      username: 'reviewer_01',
      displayName: '审核员',
      expiresAt: '2026-09-12T00:00:00Z',
    }, 201))
    vi.stubGlobal('fetch', fetchMock)

    await registerAccount({ username: 'reviewer_01', displayName: '审核员', password: 'password1' })

    expect(isAuthenticated()).toBe(true)
    expect(fetchMock).toHaveBeenCalledWith('/v1/auth/register', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ username: 'reviewer_01', password: 'password1', displayName: '审核员' }),
    }))
  })

  it('maps a duplicate-account conflict from Java', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({
      code: 'ACCOUNT_ALREADY_EXISTS',
      message: 'account already exists',
    }, 409)))

    await expect(registerAccount({ username: 'reviewer_01', displayName: '重复', password: 'password1' }))
      .rejects.toThrow('该账号已被注册')
    expect(isAuthenticated()).toBe(false)
  })

  it('rejects a wrong password and accepts a matching login', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ code: 'INVALID_CREDENTIALS', message: 'invalid credentials' }, 401))
      .mockResolvedValueOnce(jsonResponse({
        token: 'tok-2',
        username: 'reviewer_01',
        displayName: '审核员',
      }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(loginAccount('reviewer_01', 'wrongpass')).rejects.toThrow('账号或密码不正确')
    expect(isAuthenticated()).toBe(false)
    await loginAccount('reviewer_01', 'password1')
    expect(isAuthenticated()).toBe(true)
    expect(fetchMock).toHaveBeenLastCalledWith('/v1/auth/login', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ username: 'reviewer_01', password: 'password1' }),
    }))
  })

  it('revokes the server session on logout', async () => {
    localStorage.setItem('lexcyber.session', JSON.stringify({
      token: 'tok-3', username: 'reviewer_01', displayName: '审核员',
    }))
    restoreSession()
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    await logout()

    expect(isAuthenticated()).toBe(false)
    expect(fetchMock).toHaveBeenCalledWith('/v1/auth/logout', expect.objectContaining({ method: 'POST' }))
  })

  it('only allows in-app redirect paths', () => {
    expect(safeRedirect('https://example.com')).toBe('/')
    expect(safeRedirect('//evil')).toBe('/')
    expect(safeRedirect('/login')).toBe('/')
    expect(safeRedirect('/tasks')).toBe('/tasks')
  })

  it('turns a network failure into the same user-facing error wrapper', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))
    await expect(loginAccount('reviewer_01', 'password1')).rejects.toBeInstanceOf(Error)
    await expect(loginAccount('reviewer_01', 'password1')).rejects.not.toBeInstanceOf(ApiError)
  })
})
