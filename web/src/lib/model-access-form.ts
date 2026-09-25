import type { ModelAccessConfigUpdate, ModelProvider } from '../api-types'

export type ModelAccessFormState = {
  provider: ModelProvider
  modelName: string
  apiBaseUrl: string
  apiKey: string
  /** 输入框保留原始文本，提交前再转换为数值。 */
  timeoutSeconds: string
}

export type FieldErrors = Partial<Record<keyof ModelAccessFormState, string>>

const MODEL_PROVIDERS: readonly ModelProvider[] = ['stub', 'openai']

const VALIDATION_MESSAGES = {
  provider: '请选择模型供应商。',
  modelName: '真实模型模式下必须填写模型名称。',
  apiBaseUrlRequired: '真实模型模式下必须填写 API Base URL。',
  apiBaseUrlFormat: 'API Base URL 必须以 http:// 或 https:// 开头。',
  apiKey: '真实模型模式下必须填写 API Key；服务端未保存任何密钥。',
  timeoutSeconds: '超时秒数必须是大于 0 的数值。',
} as const

function text(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function isModelProvider(value: unknown): value is ModelProvider {
  return MODEL_PROVIDERS.includes(value as ModelProvider)
}

/**
 * 按模型接入表单的六条规则校验字段。
 * 校验函数只返回字段错误，不执行请求或修改输入状态。
 */
export function validate(state: ModelAccessFormState, apiKeyConfigured: boolean): FieldErrors {
  const errors: FieldErrors = {}
  const provider = state?.provider as unknown
  const modelName = text(state?.modelName)
  const apiBaseUrl = text(state?.apiBaseUrl)
  const apiKey = text(state?.apiKey)
  const timeoutSeconds = Number(text(state?.timeoutSeconds))

  if (!isModelProvider(provider)) {
    errors.provider = VALIDATION_MESSAGES.provider
  }

  if (provider === 'openai' && modelName.trim() === '') {
    errors.modelName = VALIDATION_MESSAGES.modelName
  }

  const trimmedApiBaseUrl = apiBaseUrl.trim()
  if (provider === 'openai' && trimmedApiBaseUrl === '') {
    errors.apiBaseUrl = VALIDATION_MESSAGES.apiBaseUrlRequired
  } else if (trimmedApiBaseUrl !== '' && !/^https?:\/\//.test(trimmedApiBaseUrl)) {
    errors.apiBaseUrl = VALIDATION_MESSAGES.apiBaseUrlFormat
  }

  if (provider === 'openai' && !apiKeyConfigured && apiKey.trim() === '') {
    errors.apiKey = VALIDATION_MESSAGES.apiKey
  }

  if (!Number.isFinite(timeoutSeconds) || timeoutSeconds <= 0) {
    errors.timeoutSeconds = VALIDATION_MESSAGES.timeoutSeconds
  }

  return errors
}

const ERROR_HINTS: Record<string, string> = {
  MODEL_NOT_CONFIGURED:
    '服务端未取到可用的 API Key。请确认已保存 API Key，且模型供应商不是 stub；若刚保存过，请重试一次验证。',
  MODEL_TIMEOUT:
    '模型端点在超时时间内没有返回。请确认 API Base URL 可从服务器访问，或把超时秒数调大后重试。',
  MODEL_FAILED:
    '模型端点返回了错误或连接失败。请核对 API Base URL、模型名称与 API Key 是否匹配该供应商。',
}

/** 为模型探针错误提供稳定的中文处置提示；对非字符串输入也安全返回兜底文案。 */
export function errorHint(errorCode: unknown): string {
  if (typeof errorCode !== 'string') {
    return '验证未通过，服务端未返回错误码。请查看任务详情页的完整记录。'
  }

  const code = errorCode.trim()
  if (!code) {
    return '验证未通过，服务端未返回错误码。请查看任务详情页的完整记录。'
  }

  if (Object.prototype.hasOwnProperty.call(ERROR_HINTS, code)) {
    return ERROR_HINTS[code]
  }
  return `验证未通过，错误码：${code}。请查看任务详情页的完整记录。`
}

export type ModelAccessSubmitOptions = {
  /** true 时显式清除服务端已保存的 API Key；false/省略时保留它。 */
  clearApiKey?: boolean
}

/**
 * 把表单状态投影为公开接口允许的五个字段。
 * 空 API Key 默认省略；只有显式 clearApiKey 才发送 apiKey: ''。
 * 第二参数同时接受布尔值，便于调用方直接表达显式清除动作。
 */
export function toModelAccessConfigUpdate(
  state: ModelAccessFormState,
  options: ModelAccessSubmitOptions | boolean = false,
): ModelAccessConfigUpdate {
  const clearApiKey = typeof options === 'boolean' ? options : options?.clearApiKey === true
  const payload: ModelAccessConfigUpdate = {
    provider: state.provider,
    modelName: state.modelName,
    apiBaseUrl: state.apiBaseUrl,
    timeoutSeconds: Number(state.timeoutSeconds),
  }
  const apiKey = text(state.apiKey)

  if (apiKey !== '') {
    payload.apiKey = apiKey
  } else if (clearApiKey) {
    payload.apiKey = ''
  }

  return payload
}
