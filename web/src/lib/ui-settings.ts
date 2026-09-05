export type UiSettings = {
  theme: 'aurora' | 'ember' | 'tide'
  layout: 'top' | 'side'
  density: 'compact' | 'comfortable' | 'spacious'
}

const KEY = 'lexcyber.ui-settings'

export const DEFAULT_SETTINGS: UiSettings = {
  theme: 'aurora',
  layout: 'top',
  density: 'comfortable',
}

export function loadSettings(): UiSettings {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) || '{}') as Partial<UiSettings>
    return { ...DEFAULT_SETTINGS, ...raw }
  } catch {
    return { ...DEFAULT_SETTINGS }
  }
}

export function saveSettings(settings: UiSettings) {
  localStorage.setItem(KEY, JSON.stringify(settings))
  applySettings(settings)
  window.dispatchEvent(new Event('lexcyber-settings'))
}

export function applySettings(settings: UiSettings) {
  const root = document.documentElement
  root.dataset.theme = settings.theme
  root.dataset.density = settings.density
  root.dataset.layout = settings.layout
}
