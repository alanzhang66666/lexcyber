/** 从解析正文抽取日期/金额候选。启发式正则，仅作材料对照，不作为已核对事实。 */

export type ExtractKind = 'date' | 'amount'

export type ExtractCandidate = {
  kind: ExtractKind
  value: string
  locator: string | null
}

export type ExtractGroup = {
  documentId: string
  filename: string
  candidates: ExtractCandidate[]
}

type Paragraph = { paragraph?: number; text?: string; locator?: string }

const DATE_PATTERN = /(?:\d{4}年\d{1,2}月(?:\d{1,2}日)?|\d{4}[\-/]\d{1,2}(?:[\-/]\d{1,2})?)/g
const AMOUNT_PATTERN =
  /(?:(?:人民币|RMB|CNY|USD|\$|¥|￥)\s*)?\d[\d,]*(?:\.\d+)?\s*(?:亿元|万元|万余元|元|dollars?)/gi

const DEFAULT_LIMIT = 12

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function paragraphsOf(content: Record<string, unknown>): Paragraph[] {
  const raw = content.paragraphs
  if (!Array.isArray(raw)) return []
  return raw.flatMap((item, index) => {
    if (!isRecord(item)) return []
    return [{
      paragraph: typeof item.paragraph === 'number' ? item.paragraph : index + 1,
      text: typeof item.text === 'string' ? item.text : undefined,
      locator: typeof item.locator === 'string' ? item.locator : undefined,
    }]
  })
}

function locatorForValue(value: string, paragraphs: Paragraph[]): string | null {
  const index = paragraphs.findIndex((paragraph) => paragraph.text?.includes(value))
  if (index < 0) return null
  const paragraph = paragraphs[index]
  return paragraph.locator || `paragraph:${paragraph.paragraph ?? index + 1}`
}

function pushUnique(out: ExtractCandidate[], item: ExtractCandidate) {
  if (out.some((existing) => existing.kind === item.kind && existing.value === item.value && existing.locator === item.locator)) {
    return
  }
  out.push(item)
}

export function extractCandidatesFromParse(content: unknown, limit = DEFAULT_LIMIT): ExtractCandidate[] {
  if (!isRecord(content) || limit <= 0) return []
  const paragraphs = paragraphsOf(content)
  const text = typeof content.text === 'string' && content.text.trim()
    ? content.text
    : paragraphs.map((paragraph) => paragraph.text || '').join('\n')
  if (!text.trim()) return []

  const out: ExtractCandidate[] = []
  for (const match of text.matchAll(new RegExp(DATE_PATTERN.source, DATE_PATTERN.flags))) {
    const value = match[0]
    pushUnique(out, { kind: 'date', value, locator: locatorForValue(value, paragraphs) })
    if (out.length >= limit) return out
  }
  for (const match of text.matchAll(new RegExp(AMOUNT_PATTERN.source, AMOUNT_PATTERN.flags))) {
    const value = match[0]
    pushUnique(out, { kind: 'amount', value, locator: locatorForValue(value, paragraphs) })
    if (out.length >= limit) return out
  }
  return out
}

export function isExtractedFactKey(key: string | undefined): boolean {
  return Boolean(key && key.startsWith('extracted_'))
}
