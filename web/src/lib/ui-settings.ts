export type UiSettings = {
  theme: 'aurora' | 'ember' | 'tide'
  density: 'compact' | 'comfortable' | 'spacious'
}

const KEY = 'lexcyber.ui-settings'

export const DEFAULT_SETTINGS: UiSettings = {
  theme: 'aurora',
  density: 'comfortable',
}

export function loadSettings(): UiSettings {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) || '{}') as Partial<UiSettings>
    return {
      theme: raw.theme ?? DEFAULT_SETTINGS.theme,
      density: raw.density ?? DEFAULT_SETTINGS.density,
    }
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
  delete root.dataset.layout
}
