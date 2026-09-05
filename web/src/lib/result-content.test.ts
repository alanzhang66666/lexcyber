import { describe, expect, it } from 'vitest'
import { asStubResult } from './result-content'

describe('asStubResult', () => {
  it('reads the stub workflow payload as structured fields', () => {
    expect(asStubResult({
      summary: '核验资金链路',
      status: 'NEED_HUMAN',
      human_approval_required: true,
      runner: 'stub',
    })).toMatchObject({
      summary: '核验资金链路',
      human_approval_required: true,
      runner: 'stub',
    })
  })

  it('leaves unknown payloads to the raw renderer', () => {
    expect(asStubResult({ ok: true })).toBeNull()
    expect(asStubResult('text')).toBeNull()
  })
})
