import type {
  AmountEntry,
  AnalysisFact,
  Blocker,
  CandidatePath,
  CandidatePathKind,
  EvidenceRef,
  ModuleApplicability,
  SentencingParameter,
  SentencingResult,
  SentencingStep,
  VerificationStatus,
} from '../api-types'

/**
 * 把 ModuleStateView.content（Record<string, unknown>）归一化成 T2 展示类型。
 * T3 的精确 JSON key 尚未会签，这里用**容错读取**：对每个字段尝试若干候选 key，
 * 取第一个命中的。等 T3 样例到位后只需调整这里的候选 key，页面与组件不改。
 */

type Rec = Record<string, unknown>

const STATUS_VALUES: VerificationStatus[] = ['candidate', 'baseline_asserted', 'confirmed', 'rejected', 'conflicted']
const PATH_KINDS: CandidatePathKind[] = ['candidate', 'alternative', 'excluded']

function isRecord(v: unknown): v is Rec {
  return Boolean(v) && typeof v === 'object' && !Array.isArray(v)
}

function asArray(v: unknown): unknown[] {
  return Array.isArray(v) ? v : []
}

function pick(obj: Rec, keys: string[]): unknown {
  for (const k of keys) {
    const v = obj[k]
    if (v !== undefined && v !== null) return v
  }
  return undefined
}

function str(v: unknown): string | undefined {
  return typeof v === 'string' && v.length > 0 ? v : undefined
}

function num(v: unknown): number | null {
  if (typeof v === 'number' && Number.isFinite(v)) return v
  if (typeof v === 'string' && v.trim() !== '' && Number.isFinite(Number(v))) return Number(v)
  return null
}

function statusOf(v: unknown): VerificationStatus | null {
  const s = str(v)
  return s && (STATUS_VALUES as string[]).includes(s) ? (s as VerificationStatus) : null
}

/** 证据引用：支持/相反证据可能是 id 数组，也可能是对象数组。 */
function toEvidence(v: unknown): EvidenceRef[] {
  return asArray(v).map((item): EvidenceRef => {
    if (isRecord(item)) {
      return {
        id: str(pick(item, ['id', 'evidence_id', 'evidenceId', 'source_id'])),
        quote: str(pick(item, ['quote', 'text', 'excerpt', 'summary'])),
        locator: str(pick(item, ['locator', 'locatorRef', 'source_locator'])),
        documentId: str(pick(item, ['document_id', 'documentId', 'doc_id'])),
      }
    }
    return { id: str(item) }
  })
}

/** 模块结果里的事实清单（T3 `facts[].stage/verification_status/locator`）。 */
export function toAnalysisFacts(content: Rec): AnalysisFact[] {
  const raw = pick(content, ['facts', 'factItems', 'findings'])
  if (raw === undefined) return []
  return asArray(raw).flatMap((item): AnalysisFact[] => {
    if (!isRecord(item)) return []
    return [{
      id: str(pick(item, ['id', 'fact_id', 'factId'])),
      stage: str(pick(item, ['stage', 'phase', 'behavior_stage'])),
      statement: str(pick(item, ['statement', 'text', 'value', 'content', 'description', 'claim'])) ?? '',
      locator: str(pick(item, ['locator', 'locatorRef', 'source_locator'])),
      sourceDocumentId: str(pick(item, ['source_document_id', 'sourceDocumentId', 'document_id'])),
      status: statusOf(pick(item, ['verification_status', 'verificationStatus', 'status'])),
    }]
  }).filter((item) => item.statement)
}

/** 模块结果里的候选路径（候选/替代/排除，支持/相反证据并列）。 */
export function toCandidatePaths(content: Rec): CandidatePath[] {
  let raw = pick(content, ['candidate_paths', 'candidatePaths', 'paths'])
  if (raw === undefined) {
    const analyses = pick(content, ['analyses', 'analysis'])
    if (isRecord(analyses)) raw = pick(analyses, ['candidate_paths', 'candidatePaths', 'paths'])
  }
  if (raw === undefined) return []
  return asArray(raw).flatMap((item): CandidatePath[] => {
    if (!isRecord(item)) return []
    const kindRaw = str(pick(item, ['kind', 'path_kind', 'pathKind', 'type']))
    return [{
      id: str(pick(item, ['id', 'path_id', 'pathId'])),
      title: str(pick(item, ['title', 'name', 'charge', 'path', 'label'])) ?? '未命名路径',
      kind: kindRaw && (PATH_KINDS as string[]).includes(kindRaw) ? (kindRaw as CandidatePathKind) : null,
      summary: str(pick(item, ['summary', 'reasoning', 'description', 'basis', 'conclusion'])),
      supporting: toEvidence(pick(item, ['supporting', 'supporting_evidence', 'supporting_evidence_ids', 'supportingEvidenceIds'])),
      contrary: toEvidence(pick(item, ['contrary', 'contrary_evidence', 'contrary_evidence_ids', 'contraryEvidenceIds', 'opposing'])),
      status: statusOf(pick(item, ['verification_status', 'verificationStatus', 'status'])),
    }]
  })
}

/** 模块结果里的金额口径（八类分开展示，不互换）。 */
export function toAmounts(content: Rec): AmountEntry[] {
  const raw = pick(content, ['amounts', 'amount_breakdown', 'amountBreakdown', 'money_breakdown'])
  if (raw === undefined) return []
  return asArray(raw).flatMap((item): AmountEntry[] => {
    if (!isRecord(item)) return []
    const kind = str(pick(item, ['kind', 'amount_kind', 'amountKind', 'type']))
    if (!kind) return []
    return [{
      kind: kind as AmountEntry['kind'],
      label: str(pick(item, ['label', 'name', 'title'])),
      value: num(pick(item, ['value', 'amount', 'total', 'sum'])),
      currency: str(pick(item, ['currency', 'ccy', 'currency_code'])),
      locator: str(pick(item, ['locator', 'locatorRef', 'source_locator'])),
      status: statusOf(pick(item, ['verification_status', 'verificationStatus', 'status'])),
    }]
  })
}

/** 量刑 blocked 时的阻断项。 */
export function toBlockers(content: Rec): Blocker[] {
  const raw = pick(content, ['blockers', 'blocking_issues', 'blockingIssues', 'blocks'])
  if (raw === undefined) return []
  return asArray(raw).flatMap((item): Blocker[] => {
    if (!isRecord(item)) return []
    return [{
      code: str(pick(item, ['code', 'blocker_code', 'reason_code'])),
      path: str(pick(item, ['path', 'field', 'key'])),
      message: str(pick(item, ['message', 'reason', 'description', 'hint'])),
    }]
  })
}

/** 量刑结果：blocked 时只保留阻断项；其余字段容错读取。 */
export function toSentencing(content: Rec): SentencingResult {
  const parameters = asArray(pick(content, ['parameters', 'params'])).flatMap((item): SentencingParameter[] => {
    if (!isRecord(item)) return []
    return [{ name: str(pick(item, ['name', 'label', 'key'])), value: str(pick(item, ['value', 'selected', 'setting'])) }]
  })
  const steps = asArray(pick(content, ['steps', 'calculation_steps', 'calculationSteps'])).flatMap((item): SentencingStep[] => {
    if (!isRecord(item)) return []
    return [{
      label: str(pick(item, ['label', 'name', 'title', 'stage'])),
      detail: str(pick(item, ['detail', 'description', 'reason'])),
      value: str(pick(item, ['value', 'result', 'outcome'])),
    }]
  })
  const missing = asArray(pick(content, ['missing', 'missing_fields', 'missingFields', 'missing_items']))
    .map((item) => (typeof item === 'string' ? item : JSON.stringify(item)))
    .filter(Boolean)
  return {
    ruleVersion: str(pick(content, ['rule_version', 'ruleVersion', 'rules_version', 'version'])) ?? null,
    parameters,
    steps,
    interval: str(pick(content, ['interval', 'range', 'sentence_range', 'sentenceRange', 'recommended_range'])) ?? null,
    missing,
    amounts: toAmounts(content),
    blockers: toBlockers(content),
  }
}

export const APPLICABILITY_LABEL: Record<ModuleApplicability, string> = {
  unknown: '待判断',
  not_applicable: '不适用',
  limited_context: '有限语境',
  applicable: '适用',
}
