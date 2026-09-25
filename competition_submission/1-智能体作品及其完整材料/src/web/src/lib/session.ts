import { ref } from 'vue'

export type Session = {
  token: string
  username: string
  displayName: string
}

export const SESSION_KEY = 'lexcyber.session'
const LEGACY_ACCOUNTS_KEY = 'lexcyber.accounts'

export const session = ref<Session | null>(readSession())

function readJson<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    return raw ? JSON.parse(raw) as T : fallback
  } catch {
    return fallback
  }
}

function readSession(): Session | null {
  const raw = readJson<Partial<Session> | null>(SESSION_KEY, null)
  if (raw && typeof raw.token === 'string' && raw.token && typeof raw.username === 'string' && typeof raw.displayName === 'string') {
    return { token: raw.token, username: raw.username, displayName: raw.displayName }
  }
  return null
}

export function restoreSession() {
  session.value = readSession()
}

export function isAuthenticated() {
  return Boolean(readSession())
}

export function getAccessToken() {
  return readSession()?.token ?? null
}

export function persistSession(next: Session | null) {
  localStorage.removeItem(LEGACY_ACCOUNTS_KEY)
  if (next) localStorage.setItem(SESSION_KEY, JSON.stringify(next))
  else localStorage.removeItem(SESSION_KEY)
  session.value = next
}

export function safeRedirect(raw: unknown) {
  if (typeof raw !== 'string' || !raw.startsWith('/') || raw.startsWith('//') || raw.startsWith('/login')) return '/'
  return raw
}
