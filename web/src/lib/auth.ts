import { ApiError, api } from '../api'
import type { SessionView } from '../api-types'
import {
  getAccessToken,
  isAuthenticated,
  persistSession,
  restoreSession,
  safeRedirect,
  session,
  type Session,
} from './session'

export {
  getAccessToken,
  isAuthenticated,
  persistSession,
  restoreSession,
  safeRedirect,
  session,
}
export type { Session }

function persistFromApi(view: SessionView, fallbackToken?: string | null) {
  const token = view.token || fallbackToken
  if (!token) throw new Error('登录响应缺少会话令牌。')
  persistSession({ token, username: view.username, displayName: view.displayName })
}

function authError(error: unknown): Error {
  if (error instanceof ApiError) {
    if (error.code === 'ACCOUNT_ALREADY_EXISTS' || error.status === 409) {
      return new Error('该账号已被注册。')
    }
    if (error.code === 'INVALID_CREDENTIALS' || error.status === 401) {
      return new Error('账号或密码不正确。')
    }
    if (error.status === 400 && /username/i.test(error.message)) {
      return new Error('账号需为 3～32 位字母、数字或下划线。')
    }
    return new Error(error.message)
  }
  return error instanceof Error ? error : new Error('无法完成该操作。')
}

export async function registerAccount(input: { username: string; displayName: string; password: string }) {
  const username = input.username.trim()
  const displayName = input.displayName.trim() || username
  const password = input.password
  if (!/^[a-zA-Z0-9_]{3,32}$/.test(username)) {
    throw new Error('账号需为 3～32 位字母、数字或下划线。')
  }
  if (password.length < 8) throw new Error('密码至少 8 位。')
  try {
    persistFromApi(await api.register({ username, password, displayName }))
  } catch (error) {
    throw authError(error)
  }
}

export async function loginAccount(username: string, password: string) {
  if (password.length < 8) throw new Error('账号或密码不正确。')
  try {
    persistFromApi(await api.login({ username: username.trim(), password }))
  } catch (error) {
    throw authError(error)
  }
}

export async function logout() {
  try {
    if (getAccessToken()) await api.logout()
  } catch {
    // Local sign-out still proceeds if the token is already gone on the server.
  }
  persistSession(null)
}

export async function refreshSession() {
  const token = getAccessToken()
  if (!token) return
  try {
    persistFromApi(await api.getSession(), token)
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) persistSession(null)
  }
}
