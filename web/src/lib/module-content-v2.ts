import type {
  AmountEntry,
  Blocker,
  CandidatePath,
  EvidenceRef,
  SentencingResult,
  SentencingRuleResult,
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
  candidatePaths: V2CandidatePath[]
  pathDiagnostics: V2PathDiagnostic[]
  requestedCharges: V2RequestedCharge[]
  chargeCoverage: V2ChargeCoverage[]
  coverageMissingItems: V2ChargeCoverageMissingItem[]
  coverageDiagnostics: V2PathDiagnostic[]
}

export interface V2RequestedCharge {
  requestedCharge: string
  chargeKey: string | null
}

export interface V2ChargeRuleVersion {
  ruleId: string
  ruleVersion: string
  contentHash: string
  sourceIds: string[]
}

export interface V2ChargeCoverage {
  point: V2CandidatePathPoint
  date: string
  requestedCharge: string
  chargeKey: string | null
  covered: boolean
  ruleVersions: V2ChargeRuleVersion[]
}

export interface V2ChargeCoverageMissingItem {
  id: string
  missingItem: 'charge_out_of_coverage'
  kind: 'charge_out_of_coverage'
  requestedCharge: string | null
  chargeKey: string | null
  point: V2CandidatePathPoint
  date: string
  status: 'blocked'
  reason: string
}

export type V2CandidatePathPosition = 'candidate' | 'alternative_to_examine' | 'excluded' | null
export type V2CandidatePathPoint = 'as_of' | 'conduct' | 'judgment'
export type V2CandidatePathStatus = 'candidate' | 'conflicted'
export type V2CandidatePathCalculationStatus = 'calculated' | 'blocked'

export interface V2CandidatePath {
  id: string
  pathId: string
  actorId: string
  label: string
  chargeKey: string
  baselinePosition: V2CandidatePathPosition
  supportingEvidenceIds: string[]
  contraryEvidenceIds: string[]
  legalSourceIds: string[]
  ruleId: string
  ruleVersion: string
  point: V2CandidatePathPoint
  verificationStatus: V2CandidatePathStatus
  status: V2CandidatePathCalculationStatus
  exclusionReason: string | null
  blockers: V2BlockerItem[]
}

export interface V2PathDiagnostic {
  path: string
  message: string
}

function parseChargeCoverage(content: Rec): {
  requestedCharges: V2RequestedCharge[]
  chargeCoverage: V2ChargeCoverage[]
  missingItems: V2ChargeCoverageMissingItem[]
  diagnostics: V2PathDiagnostic[]
  present: boolean
} {
  const fieldsPresent = ['requested_charges', 'charge_coverage', 'missing_items'].some((key) => own(content, key))
  if (!fieldsPresent) return { requestedCharges: [], chargeCoverage: [], missingItems: [], diagnostics: [], present: false }
  const diagnostics: V2PathDiagnostic[] = []
  const requestedCharges: V2RequestedCharge[] = []
  const chargeCoverage: V2ChargeCoverage[] = []
  const missingItems: V2ChargeCoverageMissingItem[] = []
  const text = (value: unknown): string | null => typeof value === 'string' && value.trim() ? value : null
  const rawText = (value: unknown): string | null => typeof value === 'string' && value.trim() ? value : null
  const nullable = (value: unknown): string | null => value === null || value === undefined ? null : text(value)
  const point = (value: unknown): V2CandidatePathPoint | null => ['as_of', 'conduct', 'judgment'].includes(value as string) ? value as V2CandidatePathPoint : null
  const strings = (value: unknown): string[] | null => Array.isArray(value) && (value as unknown[]).every((v) => text(v) !== null) ? value as string[] : null
  const fail = (path: string, message: string) => diagnostics.push({ path, message })
  if (!['requested_charges', 'charge_coverage', 'missing_items'].every((key) => own(content, key))) {
    fail('charge_coverage', 'requested_charges、charge_coverage、missing_items 必须同时提供。')
  }
  if (own(content, 'requested_charges')) {
    if (!Array.isArray(content.requested_charges)) fail('requested_charges', 'requested_charges 必须是对象数组。')
    else content.requested_charges.forEach((value, index) => {
      const requested = isRecord(value) ? rawText(value.requestedCharge) : null
      const chargeKeyValid = isRecord(value) && (value.chargeKey === undefined || value.chargeKey === null || (typeof value.chargeKey === 'string' && rawText(value.chargeKey) !== null && Array.from(value.chargeKey).length <= 200))
      const keysValid = isRecord(value) && Object.keys(value).every((key) => key === 'requestedCharge' || key === 'chargeKey')
      if (!isRecord(value) || !requested || !chargeKeyValid || !keysValid || Array.from(requested).length > 200) {
        fail(`requested_charges[${index}]`, '请求罪名必须包含非空 requestedCharge，chargeKey 必须是字符串或 null。')
      } else requestedCharges.push({ requestedCharge: requested, chargeKey: value.chargeKey === undefined ? null : value.chargeKey as string | null })
    })
    if (requestedCharges.length > 32) fail('requested_charges', '请求罪名数量不得超过 32 项。')
    const seen = new Set<string>()
    requestedCharges.forEach((charge) => {
      const key = charge.chargeKey === null ? `raw:${charge.requestedCharge}` : `key:${charge.chargeKey}`
      if (seen.has(key)) fail('requested_charges', '请求罪名存在重复标识。')
      seen.add(key)
    })
  }
  if (own(content, 'charge_coverage')) {
    if (!Array.isArray(content.charge_coverage)) fail('charge_coverage', 'charge_coverage 必须是对象数组。')
    else content.charge_coverage.forEach((value, index) => {
      const path = `charge_coverage[${index}]`
      if (!isRecord(value) || !point(value.point) || !text(value.date) || !text(value.requested_charge) || (value.charge_key !== undefined && nullable(value.charge_key) === null && value.charge_key !== null) || typeof value.covered !== 'boolean' || !Array.isArray(value.rule_versions)) {
        fail(path, '覆盖结果字段形状无效。'); return
      }
      const versions: V2ChargeRuleVersion[] = []
      let valid = true
      ;(value.rule_versions as unknown[]).forEach((rule, ruleIndex) => {
        if (!isRecord(rule) || !text(rule.ruleId) || !text(rule.ruleVersion) || !text(rule.contentHash) || !strings(rule.sourceIds)) {
          fail(`${path}.rule_versions[${ruleIndex}]`, '规则版本字段形状无效.'); valid = false
        } else versions.push({ ruleId: text(rule.ruleId) as string, ruleVersion: text(rule.ruleVersion) as string, contentHash: text(rule.contentHash) as string, sourceIds: strings(rule.sourceIds) as string[] })
      })
      if (valid) chargeCoverage.push({ point: point(value.point) as V2CandidatePathPoint, date: text(value.date) as string, requestedCharge: text(value.requested_charge) as string, chargeKey: nullable(value.charge_key), covered: value.covered as boolean, ruleVersions: versions })
    })
  }
  if (own(content, 'missing_items')) {
    if (!Array.isArray(content.missing_items)) fail('missing_items', 'missing_items 必须是对象数组。')
    else content.missing_items.forEach((value, index) => {
      const path = `missing_items[${index}]`
      if (!isRecord(value) || !text(value.id) || value.missing_item !== 'charge_out_of_coverage' || value.kind !== 'charge_out_of_coverage' || (value.requested_charge !== null && !text(value.requested_charge)) || (value.charge_key !== undefined && nullable(value.charge_key) === null && value.charge_key !== null) || !point(value.point) || !text(value.date) || value.status !== 'blocked' || !text(value.reason)) {
        fail(path, '未覆盖请求字段形状无效。')
      } else missingItems.push({ id: text(value.id) as string, missingItem: 'charge_out_of_coverage', kind: 'charge_out_of_coverage', requestedCharge: value.requested_charge === null ? null : text(value.requested_charge), chargeKey: nullable(value.charge_key), point: point(value.point) as V2CandidatePathPoint, date: text(value.date) as string, status: 'blocked', reason: text(value.reason) as string })
    })
  }
  return { requestedCharges, chargeCoverage, missingItems, diagnostics, present: true }
}

function own(item: Rec, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(item, key)
}

function requiredText(item: Rec, key: string): string | null {
  return own(item, key) && typeof item[key] === 'string' && item[key].trim() ? item[key] as string : null
}

function strictStringArray(item: Rec, key: string): string[] | null {
  if (!own(item, key) || !Array.isArray(item[key])) return null
  const values = item[key] as unknown[]
  return values.every((v) => typeof v === 'string' && v.trim()) ? values as string[] : null
}

function hasDuplicate(values: string[]): boolean {
  return new Set(values).size !== values.length
}

function parseV2CandidatePath(item: Rec, index: number): { path?: V2CandidatePath; diagnostic?: V2PathDiagnostic } {
  const prefix = `candidate_paths[${index}]`
  const fail = (message: string) => ({ diagnostic: { path: prefix, message } })
  const id = requiredText(item, 'id')
  const pathId = requiredText(item, 'path_id')
  const actorId = requiredText(item, 'actor_id')
  const label = requiredText(item, 'label')
  if (!id || !pathId || !actorId || !label) return fail('缺少必需的 id、path_id、actor_id 或 label。')
  const chargeKey = requiredText(item, 'charge_key')
  const baseline = item.baseline_position
  if (!own(item, 'charge_key') || chargeKey === null) return fail('charge_key 必须是非空字符串。')
  if (!own(item, 'baseline_position') || !['candidate', 'alternative_to_examine', 'excluded', null].includes(baseline as never)) return fail('baseline_position 不是有效值。')
  const supporting = strictStringArray(item, 'supporting_evidence_ids')
  const contrary = strictStringArray(item, 'contrary_evidence_ids')
  const legal = strictStringArray(item, 'legal_source_ids')
  if (!supporting || !contrary || !legal) return fail('supporting_evidence_ids、contrary_evidence_ids、legal_source_ids 必须是字符串数组。')
  const ruleId = requiredText(item, 'rule_id')
  const ruleVersion = requiredText(item, 'rule_version')
  if (!ruleId || !ruleVersion) return fail('rule_id 与 rule_version 必须是非空字符串。')
  const point = item.point
  if (!['as_of', 'conduct', 'judgment'].includes(point as string)) return fail('point 不是有效值。')
  const verificationStatus = item.verification_status
  if (!['candidate', 'conflicted'].includes(verificationStatus as string)) return fail('verification_status 不是有效值。')
  const status = item.status
  if (!['calculated', 'blocked'].includes(status as string)) return fail('status 不是有效值。')
  const exclusionReason = item.exclusion_reason
  if (!own(item, 'exclusion_reason') || (exclusionReason !== null && typeof exclusionReason !== 'string')) return fail('exclusion_reason 必须是字符串或 null。')
  if (baseline === 'excluded' && !(typeof exclusionReason === 'string' && exclusionReason.trim())) return fail('excluded 路径必须提供非空 exclusion_reason。')
  if (!own(item, 'blockers') || !Array.isArray(item.blockers) || (item.blockers as unknown[]).some((b) => !isRecord(b))) return fail('blockers 必须是对象数组。')
  if (hasDuplicate(supporting) || hasDuplicate(contrary) || hasDuplicate(legal)) return fail('证据或法源引用存在重复 ID。')
  const blockerItems = (item.blockers as Rec[]).map(toBlockerItem)
  const hasMeaningfulBlocker = blockerItems.some((b) => Boolean(b.code || b.path || b.message || b.reason))
  if (status === 'calculated' && (baseline === null || blockerItems.length > 0)) return fail('calculated 路径必须有基准位置且不得包含阻断项。')
  if (status === 'blocked' && (baseline !== null || exclusionReason !== null || !hasMeaningfulBlocker)) return fail('blocked 路径不得声明基准位置或排除理由，且必须提供有效阻断项。')
  if (verificationStatus === 'conflicted' && status === 'calculated') return fail('conflicted 路径不得处于 calculated 状态。')
  return { path: {
    id, pathId, actorId, label, chargeKey,
    baselinePosition: baseline as V2CandidatePathPosition,
    supportingEvidenceIds: supporting, contraryEvidenceIds: contrary, legalSourceIds: legal,
    ruleId, ruleVersion, point: point as V2CandidatePathPoint,
    verificationStatus: verificationStatus as V2CandidatePathStatus,
    status: status as V2CandidatePathCalculationStatus,
    exclusionReason: exclusionReason as string | null,
    blockers: blockerItems,
  } }
}

export function toV2CandidatePaths(content: Rec): { paths: V2CandidatePath[]; diagnostics: V2PathDiagnostic[]; present: boolean } {
  if (str(content.schema_version) !== 'case.conviction.v2') return { paths: [], diagnostics: [], present: false }
  if (!own(content, 'candidate_paths')) return { paths: [], diagnostics: [], present: false }
  if (!Array.isArray(content.candidate_paths)) return { paths: [], diagnostics: [{ path: 'candidate_paths', message: 'candidate_paths 必须是对象数组。' }], present: true }
  const paths: V2CandidatePath[] = []
  const diagnostics: V2PathDiagnostic[] = []
  content.candidate_paths.forEach((value, index) => {
    if (!isRecord(value)) { diagnostics.push({ path: `candidate_paths[${index}]`, message: '路径必须是对象。' }); return }
    const parsed = parseV2CandidatePath(value, index)
    if (parsed.path) paths.push(parsed.path)
    if (parsed.diagnostic) diagnostics.push(parsed.diagnostic)
  })
  return { paths, diagnostics, present: true }
}

function sharedCandidatePath(path: V2CandidatePath): CandidatePath {
  const kind = path.baselinePosition === 'alternative_to_examine' ? 'alternative' : path.baselinePosition
  return {
    id: `${path.id}:${path.actorId}:${path.point}`, title: path.label, kind,
    actorId: path.actorId, chargeKey: path.chargeKey,
    supporting: path.supportingEvidenceIds.map((id): EvidenceRef => ({ id })),
    contrary: path.contraryEvidenceIds.map((id): EvidenceRef => ({ id })),
    legalSourceIds: path.legalSourceIds, ruleId: path.ruleId, ruleVersion: path.ruleVersion, point: path.point,
    status: path.verificationStatus, calculationStatus: path.status,
    exclusionReason: path.baselinePosition === 'excluded' ? path.exclusionReason : null,
    exclusionPending: path.baselinePosition === 'excluded',
    blockers: path.blockers.map((b): Blocker => ({ code: b.code, path: b.path, message: b.message ?? b.reason })),
  }
}

export function v2CandidatePathCards(content: Rec): { paths: CandidatePath[]; diagnostics: V2PathDiagnostic[]; present: boolean } {
  const parsed = toV2CandidatePaths(content)
  return { paths: parsed.paths.map(sharedCandidatePath), diagnostics: parsed.diagnostics, present: parsed.present }
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
  const parsedPaths = toV2CandidatePaths(content)
  const parsedCoverage = str(content.schema_version) === 'case.conviction.v2' ? parseChargeCoverage(content) : { requestedCharges: [], chargeCoverage: [], missingItems: [], diagnostics: [], present: false }
  return {
    schemaVersion: str(content.schema_version) ?? '',
    status: parsedPaths.diagnostics.length || parsedCoverage.diagnostics.length ? 'blocked' : (str(content.status) ?? ''),
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
    blockers: [
      ...asArray(content.blockers).map(toBlockerItem),
      ...parsedPaths.diagnostics.map((diagnostic) => ({ code: 'PATH_FORMAT_INVALID', path: diagnostic.path, message: diagnostic.message })),
      ...parsedCoverage.diagnostics.map((diagnostic) => ({ code: 'CHARGE_COVERAGE_INVALID', path: diagnostic.path, message: diagnostic.message })),
    ],
    divergence: asArray(content.divergence),
    humanReviewRequired: content.human_review_required === true,
    generatedAt: str(content.generated_at),
    candidatePaths: parsedPaths.paths,
    pathDiagnostics: parsedPaths.diagnostics,
    requestedCharges: parsedCoverage.requestedCharges,
    chargeCoverage: parsedCoverage.chargeCoverage,
    coverageMissingItems: parsedCoverage.missingItems,
    coverageDiagnostics: parsedCoverage.diagnostics,
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

function toRuleResult(result: V2SentencingComputation): SentencingRuleResult {
  const steps: SentencingStep[] = result.steps.map((s): SentencingStep => {
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
  const fine = fineText(result.fine)
  return {
    ruleId: result.ruleId || null,
    ruleVersion: result.ruleVersion || null,
    status: result.status || null,
    termMonths: result.termMonths,
    fine: fine ?? null,
    steps,
    blockers: result.blockers.map((b) => ({ code: b.code, path: b.path, message: b.message ?? b.reason })),
  }
}

/** 把 sentencing.v2 payload 映射为 SentencingResultPanel 的展示类型（严格键名）。 */
export function toSentencingResultV2(content: Rec): SentencingResult | null {
  const payload = toV2Sentencing(content)
  if (!payload) return null
  const ruleResults = payload.results.map(toRuleResult)
  const blockers: Blocker[] = [...payload.blockers, ...ruleResults.flatMap((result) => result.blockers ?? [])]
  const blocked = payload.status === 'blocked' || blockers.length > 0
  const first = ruleResults[0]
  const intervalParts: string[] = []
  if (!blocked && ruleResults.length <= 1 && first?.termMonths !== null && first?.termMonths !== undefined) {
    intervalParts.push(`${first.termMonths} 个月`)
    if (first.fine) intervalParts.push(first.fine)
  }
  if (payload.status === 'blocked' && blockers.length === 0) {
    blockers.push({ message: '量刑结果整体被阻断，未输出刑期。' })
  }
  return {
    status: payload.status || null,
    ruleVersion: first ? `${first.ruleId}@${first.ruleVersion}` : null,
    parameters: [],
    steps: blocked ? [] : (first?.steps ?? []),
    interval: intervalParts.length ? intervalParts.join('；') : null,
    missing: [],
    amounts: [],
    blockers,
    ruleResults,
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
