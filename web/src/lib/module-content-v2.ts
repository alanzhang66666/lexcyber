import type {
  AmountEntry,
  Blocker,
  SentencingResult,
  SentencingStep,
  VerificationStatus,
} from '../api-types'

/**
 * v2 工件 payload 严格读取器（无多 key 容错）。
 *
 * 只认 `contracts/public-api-v2.yaml` 冻结的 schema_version：
 * - case.compliance.v2 / case.conviction.v2（module_analysis 执行体）
 * - sentencing.v2（sentencing_v2 执行体）
 * - draft.v2（document_render 执行体）
 * 以及 case.facts 快照的 entities.amounts（FactsVersion payload）。
 *
 * /v1 模块壳与三案演示内容请用 module-content.ts（容错读取）。
 * 未识别 schema_version 一律返回 null —— 未知结构不猜读，对齐后端 fail-closed。
 */

type Rec = Record<string, unknown>

export const V2_MODULE_SCHEMAS = new Set(['case.compliance.v2', 'case.conviction.v2'])
export const V2_SENTENCING_SCHEMA = 'sentencing.v2'
export const V2_DRAFT_SCHEMA = 'draft.v2'

function isRecord(v: unknown): v is Rec {
  return Boolean(v) && typeof v === 'object' && !Array.isArray(v)
}

function asArray(v: unknown): Rec[] {
  return Array.isArray(v) ? v.filter(isRecord) : []
}

function str(v: unknown): string | undefined {
  return typeof v === 'string' && v.length > 0 ? v : undefined
}

function num(v: unknown): number | null {
  if (typeof v === 'number' && Number.isFinite(v)) return v
  if (typeof v === 'string' && v.trim() !== '' && Number.isFinite(Number(v))) return Number(v)
  return null
}

function strArray(v: unknown): string[] {
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string' && x.length > 0) : []
}

export function v2SchemaOf(content: Rec | null | undefined): string | null {
  return content ? str(content.schema_version) ?? null : null
}

function isModulePayload(content: Rec): boolean {
  return V2_MODULE_SCHEMAS.has(str(content.schema_version) ?? '')
}

// ---------------------------------------------------------------------------
// 阻断项（case.*.v2 / sentencing.v2 / draft 的 blockers 与 unresolved 同构展示）

export interface V2BlockerItem {
  code?: string
  path?: string
  message?: string
  reason?: string
}

function toBlockerItem(item: Rec): V2BlockerItem {
  return {
    code: str(item.code),
    path: str(item.path),
    message: str(item.message),
    reason: str(item.reason),
  }
}

export function v2Blockers(content: Rec): V2BlockerItem[] {
  return [...asArray(content.blockers), ...asArray(content.unresolved)].map(toBlockerItem)
}

// ---------------------------------------------------------------------------
// case.compliance.v2 / case.conviction.v2 —— 规则执行结果

export interface V2RuleTrace {
  path?: string
  op?: string
  expected?: unknown
  found?: boolean
  actual?: unknown
  result?: boolean
}

export interface V2ModuleRule {
  ruleId: string
  ruleVersion: string
  family?: string
  fired: boolean
  outcomeSummary?: string
  sourceIds: string[]
  trace: V2RuleTrace[]
}

export interface V2ModuleAnalysis {
  schemaVersion: string
  status: string
  rules: V2ModuleRule[]
  blockers: V2BlockerItem[]
  divergence: Rec[]
  humanReviewRequired: boolean
  generatedAt?: string
}

function outcomeSummary(outcome: unknown): string | undefined {
  if (outcome == null) return undefined
  if (typeof outcome === 'string') return outcome
  if (isRecord(outcome)) {
    return str(outcome.label) ?? str(outcome.charge) ?? str(outcome.summary) ?? JSON.stringify(outcome)
  }
  return String(outcome)
}

export function toV2ModuleAnalysis(content: Rec): V2ModuleAnalysis | null {
  if (!isModulePayload(content)) return null
  return {
    schemaVersion: str(content.schema_version) ?? '',
    status: str(content.status) ?? '',
    rules: asArray(content.rules).map((r): V2ModuleRule => ({
      ruleId: str(r.ruleId) ?? '',
      ruleVersion: str(r.ruleVersion) ?? '',
      family: str(r.family),
      fired: r.fired === true,
      outcomeSummary: outcomeSummary(r.outcome),
      sourceIds: strArray(r.sourceIds),
      trace: asArray(r.trace).map((t): V2RuleTrace => ({
        path: str(t.path),
        op: str(t.op),
        expected: t.expected,
        found: typeof t.found === 'boolean' ? t.found : undefined,
        actual: t.actual,
        result: typeof t.result === 'boolean' ? t.result : undefined,
      })),
    })),
    blockers: asArray(content.blockers).map(toBlockerItem),
    divergence: asArray(content.divergence),
    humanReviewRequired: content.human_review_required === true,
    generatedAt: str(content.generated_at),
  }
}

// ---------------------------------------------------------------------------
// sentencing.v2 —— 可解释量刑计算

export interface V2SentencingComputation {
  ruleId: string
  ruleVersion: string
  status: string
  termMonths: number | null
  fine?: unknown
  steps: Rec[]
  blockers: V2BlockerItem[]
}

export interface V2SentencingPayload {
  status: string
  results: V2SentencingComputation[]
  blockers: V2BlockerItem[]
  humanReviewRequired: boolean
}

export function toV2Sentencing(content: Rec): V2SentencingPayload | null {
  if (str(content.schema_version) !== V2_SENTENCING_SCHEMA) return null
  return {
    status: str(content.status) ?? '',
    results: asArray(content.results).map((r): V2SentencingComputation => ({
      ruleId: str(r.ruleId) ?? '',
      ruleVersion: str(r.ruleVersion) ?? '',
      status: str(r.status) ?? '',
      termMonths: num(r.term_months),
      fine: r.fine,
      steps: asArray(r.steps),
      blockers: asArray(r.blockers).map(toBlockerItem),
    })),
    blockers: asArray(content.blockers).map(toBlockerItem),
    humanReviewRequired: content.human_review_required === true,
  }
}

function monthsText(v: unknown): string | undefined {
  const n = num(v)
  return n === null ? undefined : `${n} 个月`
}

function fineText(fine: unknown): string | undefined {
  if (fine == null) return undefined
  if (typeof fine === 'number') return `罚金 ${fine} 元`
  if (isRecord(fine)) {
    const amount = num(fine.amount ?? fine.value)
    return amount === null ? JSON.stringify(fine) : `罚金 ${amount} 元`
  }
  return String(fine)
}

/** 把 sentencing.v2 payload 映射为 SentencingResultPanel 的展示类型（严格键名）。 */
export function toSentencingResultV2(content: Rec): SentencingResult | null {
  const payload = toV2Sentencing(content)
  if (!payload) return null
  const result = payload.results[0]
  const steps: SentencingStep[] = (result?.steps ?? []).map((s): SentencingStep => {
    const id = str(s.id)
    const operation = str(s.operation)
    const label = [id, operation].filter(Boolean).join(' · ') || undefined
    const before = monthsText(s.before_months)
    const after = monthsText(s.after_months)
    const delta = num(s.delta_months)
    const reason = str(s.reason)
    let value: string | undefined
    if (before && after) value = `${before} → ${after}`
    else if (after) value = after
    else if (delta !== null) value = `${delta > 0 ? '+' : ''}${delta} 个月`
    const sources = strArray(s.source_ids)
    return { label, detail: reason ?? (sources.length ? sources.join('、') : undefined), value }
  })
  const intervalParts: string[] = []
  if (result?.termMonths !== null && result?.termMonths !== undefined) {
    intervalParts.push(`${result.termMonths} 个月`)
  }
  const fine = fineText(result?.fine)
  if (fine) intervalParts.push(fine)
  const blockers: Blocker[] = [...payload.blockers, ...(result?.blockers ?? [])].map((b) => ({
    code: b.code,
    path: b.path,
    message: b.message ?? b.reason,
  }))
  return {
    ruleVersion: result ? `${result.ruleId}@${result.ruleVersion}` : null,
    parameters: [],
    steps,
    interval: intervalParts.length ? intervalParts.join('；') : null,
    missing: [],
    amounts: [],
    blockers,
  }
}

// ---------------------------------------------------------------------------
// draft.v2 —— 文书渲染结果

export interface V2DraftRender {
  status: string
  docType?: string
  body: string
  unresolved: V2BlockerItem[]
}

export function toV2Draft(content: Rec): V2DraftRender | null {
  if (str(content.schema_version) !== V2_DRAFT_SCHEMA) return null
  return {
    status: str(content.status) ?? '',
    docType: str(content.doc_type),
    body: typeof content.body === 'string' ? content.body : '',
    unresolved: asArray(content.unresolved).map(toBlockerItem),
  }
}

// ---------------------------------------------------------------------------
// FactsVersion payload —— entities.amounts 严格读取（金额展示口径）

const AMOUNT_STATUS: VerificationStatus[] = ['candidate', 'baseline_asserted', 'confirmed', 'rejected', 'conflicted']

export function toFactsVersionAmounts(versionPayload: Rec): AmountEntry[] {
  const entities = versionPayload.entities
  if (!isRecord(entities)) return []
  return asArray(entities.amounts).flatMap((item): AmountEntry[] => {
    const kind = str(item.kind)
    if (!kind) return []
    const status = str(item.verificationStatus)
    return [{
      kind: kind as AmountEntry['kind'],
      label: str(item.label),
      value: num(item.value),
      currency: str(item.currency),
      locator: str(item.locator),
      status: status && (AMOUNT_STATUS as string[]).includes(status) ? status as VerificationStatus : null,
    }]
  })
}
