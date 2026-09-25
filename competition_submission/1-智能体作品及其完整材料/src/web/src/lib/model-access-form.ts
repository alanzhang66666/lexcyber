import type { ModelAccessConfigUpdate, ModelProvider } from '../api-types'

export type ModelAccessFormState = {
  provider: ModelProvider
  modelName: string
  apiBaseUrl: string
  apiKey: string
  timeoutSeconds: string
}

export type FieldErrors = Partial<Record<keyof ModelAccessFormState, string>>

export function validate(state: ModelAccessFormState, apiKeyConfigured: boolean): FieldErrors {
  const errors: FieldErrors = {}
  if (!['stub', 'openai'].includes(state.provider)) errors.provider = '请选择模型供应商。'
  if (!state.modelName.trim()) errors.modelName = '请填写模型名称。'
  if (!/^https?:\/\//.test(state.apiBaseUrl.trim())) errors.apiBaseUrl = 'API Base URL 必须以 http:// 或 https:// 开头。'
  if (state.provider === 'openai' && !apiKeyConfigured && !state.apiKey.trim()) errors.apiKey = '请填写 API Key。'
  const timeout = Number(state.timeoutSeconds)
  if (!Number.isFinite(timeout) || timeout <= 0 || timeout > 600) errors.timeoutSeconds = '超时秒数应在 0 到 600 之间。'
  return errors
}

export function toModelAccessConfigUpdate(
  state: ModelAccessFormState,
  clearApiKey = false,
): ModelAccessConfigUpdate {
  const payload: ModelAccessConfigUpdate = {
    provider: state.provider,
    modelName: state.modelName.trim(),
    apiBaseUrl: state.apiBaseUrl.trim().replace(/\/$/, ''),
    timeoutSeconds: Number(state.timeoutSeconds),
  }
  if (state.apiKey) payload.apiKey = state.apiKey
  else if (clearApiKey) payload.apiKey = ''
  return payload
}
