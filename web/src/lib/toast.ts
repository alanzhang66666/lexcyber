type Listener = (message: string) => void

const listeners = new Set<Listener>()

export const PLACEHOLDER_TOAST = '该能力尚未接通，已保留界面占位。'

export function toast(message: string) {
  listeners.forEach((listener) => listener(message))
}

export function toastPlaceholder() {
  toast(PLACEHOLDER_TOAST)
}

export function onToast(listener: Listener) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}
