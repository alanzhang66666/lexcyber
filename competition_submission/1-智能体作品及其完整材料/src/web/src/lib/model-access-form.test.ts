import { describe, expect, it } from 'vitest'
import { toModelAccessConfigUpdate, validate, type ModelAccessFormState } from './model-access-form'

const valid: ModelAccessFormState = {
  provider: 'openai',
  modelName: 'deepseek-chat',
  apiBaseUrl: 'https://api.deepseek.com/v1/',
  apiKey: '',
  timeoutSeconds: '45',
}

describe('model access form', () => {
  it('requires a key only when none is already saved', () => {
    expect(validate(valid, false).apiKey).toBeTruthy()
    expect(validate(valid, true)).toEqual({})
  })

  it('omits a blank key by default and trims the endpoint', () => {
    expect(toModelAccessConfigUpdate(valid)).toEqual({
      provider: 'openai',
      modelName: 'deepseek-chat',
      apiBaseUrl: 'https://api.deepseek.com/v1',
      timeoutSeconds: 45,
    })
  })

  it('only clears the saved key when explicitly requested', () => {
    expect(toModelAccessConfigUpdate(valid, true).apiKey).toBe('')
  })
})
