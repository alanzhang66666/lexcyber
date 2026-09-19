import { describe, expect, it } from 'vitest'
import { extractCandidatesFromParse, isExtractedFactKey } from './extract-candidates'

describe('extractCandidatesFromParse', () => {
  it('pulls dates and amounts from parse paragraphs and maps locators', () => {
    const candidates = extractCandidatesFromParse({
      text: '2023年5月12日转入人民币 12万元。',
      paragraphs: [
        { paragraph: 2, text: '2023年5月12日转入人民币 12万元。', locator: 'paragraph:2' },
      ],
    })
    expect(candidates).toEqual([
      { kind: 'date', value: '2023年5月12日', locator: 'paragraph:2' },
      { kind: 'amount', value: '人民币 12万元', locator: 'paragraph:2' },
    ])
  })

  it('returns an empty list when parse content has no text', () => {
    expect(extractCandidatesFromParse({ schemaVersion: 'document.parse.v1' })).toEqual([])
    expect(extractCandidatesFromParse(null)).toEqual([])
  })

  it('recognizes stored extract fact keys', () => {
    expect(isExtractedFactKey('extracted_date')).toBe(true)
    expect(isExtractedFactKey('涉案金额')).toBe(false)
  })
})
