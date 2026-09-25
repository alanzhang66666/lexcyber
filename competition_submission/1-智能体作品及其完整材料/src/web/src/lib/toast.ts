type Listener = (message: string) => void

const listeners = new Set<Listener>()

export const PLACEHOLDER_TOAST = '请从案件中心或功能入口进入对应模块。'

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
