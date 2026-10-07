<script setup lang="ts">
import { computed } from 'vue'

type Rec = Record<string, unknown>

const props = defineProps<{ content: unknown }>()

function record(value: unknown): Rec | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Rec : null
}
function records(value: unknown): Rec[] {
  return Array.isArray(value) ? value.map(record).filter((v): v is Rec => Boolean(v)) : []
}
function text(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value : undefined
}
function number(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}
function list(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string' && v.trim().length > 0) : []
}
function labelStatus(value: unknown): string {
  if (value === 'blocked') return '已阻断'
  if (value === 'calculated') return '已计算'
  if (value === 'not_applicable') return '不适用'
  return text(value) ?? '未知状态'
}
function displayValue(value: unknown): string {
  if (value === undefined || value === null || value === '') return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}
function fineValue(value: unknown): string | undefined {
  const item = record(value)
  if (item) {
    const amount = number(item.amount ?? item.value)
    return amount === undefined ? text(item.label) ?? displayValue(value) : `罚金 ${amount} 元`
  }
  if (typeof value === 'number' && Number.isFinite(value)) return `罚金 ${value} 元`
  return text(value)
}

const payload = computed(() => record(props.content))
const paths = computed(() => records(payload.value?.temporal_paths))
const sources = computed(() => records(payload.value?.source_resolutions))
const hasTemporal = computed(() => paths.value.length > 0 || sources.value.length > 0)
const topBlocked = computed(() => payload.value?.status === 'blocked')

function pathLabel(path: Rec): string {
  return path.point === 'conduct' ? '行为时点' : path.point === 'judgment' ? '裁判时点' : text(path.point) ?? '法律时点'
}
function pathRules(path: Rec): Rec[] {
  return [...records(path.rules), ...records(path.results)]
}
function pathBlocked(path: Rec): boolean {
  return path.status === 'blocked' || blockers(path).length > 0
}
function blockers(path: Rec): Rec[] {
  const items = [...records(path.blockers)]
  for (const rule of pathRules(path)) {
    items.push(...records(rule.blockers))
    const evidence = ruleEvidence(rule)
    items.push(...records(evidence?.blockers))
    for (const kind of list(evidence?.missingKinds ?? evidence?.missingRequiredKinds)) {
      items.push({ code: 'RULE_EVIDENCE_MISSING', message: `缺少必需证据类型 ${kind}` })
    }
    for (const kind of list(evidence?.unconfirmedKinds)) {
      items.push({ code: 'RULE_EVIDENCE_UNCONFIRMED', message: `以下证据类型待核实 ${kind}` })
    }
    if (rule.status === 'blocked' && !items.length) {
      items.push({ code: 'RULE_BLOCKED', message: '规则分支已阻断' })
    }
  }
  return items
}
function blockerText(item: Rec): string {
  return text(item.message) ?? text(item.reason) ?? text(item.code) ?? text(item.path) ?? '待确认项'
}
function ruleId(rule: Rec): string {
  return [text(rule.ruleId), text(rule.ruleVersion)].filter(Boolean).join('@') || '未命名规则'
}
function ruleEvidence(rule: Rec): Rec | null {
  return record(rule.evidence_checks ?? rule.evidenceChecks)
}
function ruleStatus(rule: Rec): string {
  const explicit = text(rule.status)
  if (explicit) return explicit
  if (rule.fired !== true) return 'not_applicable'
  const evidence = ruleEvidence(rule)
  if (records(rule.blockers).length || records(evidence?.blockers).length
      || list(evidence?.missingKinds ?? evidence?.missingRequiredKinds).length
      || list(evidence?.unconfirmedKinds).length) return 'blocked'
  return 'calculated'
}
function outcome(rule: Rec): string | undefined {
  const raw = rule.outcome ?? rule.outcomeSummary
  if (raw === undefined || raw === null) return undefined
  if (typeof raw === 'object') {
    const item = record(raw)
    return item ? text(item.label) ?? text(item.summary) ?? text(item.charge) ?? displayValue(raw) : displayValue(raw)
  }
  return displayValue(raw)
}
function resultNumbers(rule: Rec): string[] {
  if (ruleStatus(rule) !== 'calculated' || records(rule.blockers).length > 0) return []
  const values: string[] = []
  const months = number(rule.term_months ?? rule.termMonths)
  if (months !== undefined) values.push(`刑期 ${months} 个月`)
  const fine = fineValue(rule.fine)
  if (fine) values.push(fine)
  return values
}
function sourceItems(path: Rec): Rec[] {
  const snapshot = record(path.dependency_snapshot)
  const refs = records(snapshot?.source_versions)
  const keys = refs.map((item) => text(item.sourceKey)).filter((value): value is string => Boolean(value))
  const ids = refs.map((item) => text(item.sourceId)).filter((value): value is string => Boolean(value))
  const point = text(path.point)
  const lawKey = point === 'conduct' ? 'conduct_law' : point === 'judgment' ? 'judgment_law' : ''
  const sourceHasPoint = (source: Rec): boolean => Boolean(
    (lawKey && record(source[lawKey])) || records(source.overlaps).some((overlap) => text(overlap.point) === point),
  )
  const hasPointData = Boolean(lawKey && sources.value.some(sourceHasPoint))
  const selected = sources.value.filter((source) => {
    const pointLaw = lawKey ? record(source[lawKey]) : null
    const pointLawId = text(pointLaw?.sourceId)
    const directMatch = (keys.length && keys.includes(text(source.sourceKey) ?? ''))
      || (ids.length && (ids.includes(text(source.sourceId) ?? '') || (pointLawId ? ids.includes(pointLawId) : false)))
    if (directMatch) return !hasPointData || sourceHasPoint(source)
    if (keys.length || ids.length) return false
    return !hasPointData || sourceHasPoint(source)
  })
  return selected
}
function sourceDetails(path: Rec): Rec[] {
  const lawKey = path.point === 'conduct' ? 'conduct_law' : path.point === 'judgment' ? 'judgment_law' : ''
  const candidates = sourceItems(path)
  const hasPointViews = Boolean(lawKey && candidates.some((source) => record(source[lawKey]) || records(source.overlaps).some((overlap) => text(overlap.point) === path.point)))
  return candidates.filter((source) => !hasPointViews || record(source[lawKey]) || records(source.overlaps).some((overlap) => text(overlap.point) === path.point)).flatMap((source) => {
    const law = record(source[lawKey])
    if (law) return [{ ...source, ...law, sourceKey: source.sourceKey }]
    const overlaps = records(source.overlaps)
      .filter((overlap) => text(overlap.point) === path.point)
      .flatMap((overlap) => records(overlap.candidates))
    return overlaps.length ? overlaps.map((candidate) => ({ ...source, ...candidate, sourceKey: source.sourceKey })) : [source]
  })
}
function missingKinds(source: Rec): string[] {
  const raw = source.evidence_checks ?? source.evidenceChecks
  const checks = record(raw) ? [record(raw) as Rec] : records(raw)
  return checks.flatMap((check) => {
    if (check.passed === true || check.status === 'passed') return []
    return list(check.missingKinds ?? check.missingRequiredKinds ?? check.requiredKinds)
  })
}
function ruleMissingKinds(rule: Rec): string[] {
  const evidence = ruleEvidence(rule)
  if (!evidence) return []
  const direct = list(evidence.missingKinds ?? evidence.missingRequiredKinds ?? evidence.requiredKinds)
  if (direct.length) return direct
  return records(evidence.blockers).flatMap((item) => list(item.missing_required_kinds ?? item.missingRequiredKinds))
}
function ruleUnconfirmedKinds(rule: Rec): string[] {
  return list(ruleEvidence(rule)?.unconfirmedKinds)
}
function sourceWarning(source: Rec): string | undefined {
  if (source.coverageGap === true) return '该时点存在法源覆盖缺口'
  if (Array.isArray(source.divergence) && source.divergence.length) return '行为时点与裁判时点的法源版本存在差异'
  if (source.overlap === true) return '法源有效期存在重叠，待人工核验'
  return undefined
}
</script>

<template>
  <section v-if="hasTemporal" class="panel temporal-panel" data-testid="legal-temporal-panel">
    <div class="panel-heading">
      <div><p class="section-index">时点复核</p><h2>双时点复核对照</h2></div>
      <span v-if="topBlocked" class="subtle-chip temporal-blocked">总体待确认</span>
    </div>
    <p class="panel-note">分别展示行为时点与裁判时点的法源、规则版本和计算结果；系统不替人工择定适用时点。</p>
    <div class="temporal-paths">
      <article v-for="path in paths" :key="`${path.point}-${path.as_of_date}`" class="temporal-path">
        <header class="temporal-path-heading">
          <div><p class="eyebrow">法律时点路径</p><h3>{{ pathLabel(path) }}</h3></div>
          <span class="subtle-chip" :class="pathBlocked(path) ? 'temporal-blocked' : 'temporal-calculated'">{{ labelStatus(pathBlocked(path) ? 'blocked' : path.status) }}</span>
        </header>
        <dl class="data-list inline-data temporal-meta">
          <div><dt>适用日期</dt><dd class="mono">{{ text(path.as_of_date) ?? '—' }}</dd></div>
          <div><dt>依赖规则</dt><dd>{{ pathRules(path).length }} 条</dd></div>
        </dl>
        <div v-if="sourceItems(path).length" class="temporal-sources">
          <h4>法源版本</h4>
          <ul>
            <li v-for="(source, index) in sourceDetails(path)" :key="`${text(source.sourceId) ?? text(source.sourceKey) ?? index}-${text(source.sourceVersion) ?? ''}`">
              <strong>{{ text(source.title) ?? text(source.sourceKey) ?? '未命名法源' }}</strong>
              <span v-if="source.sourceVersion" class="mono">版本 {{ source.sourceVersion }}</span>
              <span v-if="source.effectiveFrom || source.effectiveTo">有效期 {{ text(source.effectiveFrom) ?? '—' }} 至 {{ text(source.effectiveTo) ?? '—' }}</span>
              <span v-if="sourceWarning(source)">{{ sourceWarning(source) }}</span>
            </li>
          </ul>
        </div>
        <div v-if="pathBlocked(path)" class="notice notice-warning temporal-blockers" role="alert">
          <strong>该路径已阻断，暂不显示计算数字</strong>
          <ul v-if="blockers(path).length"><li v-for="(blocker, index) in blockers(path)" :key="index">{{ blockerText(blocker) }}</li></ul>
          <p v-else>请补齐该路径的适用条件后再复核。</p>
        </div>
        <div v-else class="temporal-rules">
          <h4>规则与结果</h4>
          <article v-for="(rule, index) in pathRules(path)" :key="`${ruleId(rule)}-${index}`" class="temporal-rule">
            <div class="temporal-rule-heading"><span class="mono">{{ ruleId(rule) }}</span><span>{{ labelStatus(ruleStatus(rule)) }}</span></div>
            <p v-if="outcome(rule)" class="temporal-outcome">分支结果：{{ outcome(rule) }}</p>
            <p v-if="resultNumbers(rule).length" class="temporal-numbers">{{ resultNumbers(rule).join(' · ') }}</p>
            <p v-else-if="ruleStatus(rule) === 'blocked'" class="subtle-text">该规则分支被阻断，未展示数字。</p>
            <p v-if="ruleMissingKinds(rule).length" class="temporal-evidence-line">证据审计：缺少必需证据类型 {{ ruleMissingKinds(rule).join('、') }}。</p>
            <p v-if="ruleUnconfirmedKinds(rule).length" class="temporal-evidence-line">证据审计：以下证据类型待核实 {{ ruleUnconfirmedKinds(rule).join('、') }}。</p>
          </article>
          <p v-if="!pathRules(path).length" class="subtle-text">该路径未返回逐条规则结果。</p>
        </div>
        <p v-if="topBlocked && !pathBlocked(path)" class="notice notice-info temporal-selection" role="note">
          <strong>待人工择法的路径对照，未选为结论</strong>
          <span>以上为本路径自身的计算结果，不能因为总体状态阻断而自动成为最终结论。</span>
        </p>
      </article>
    </div>
    <div v-if="sources.some((source) => missingKinds(source).length)" class="notice notice-warning temporal-evidence" role="note">
      <strong>证据审计提示</strong>
      <ul><template v-for="(source, index) in sources" :key="index"><li v-for="kind in missingKinds(source)" :key="`${index}-${kind}`">{{ text(source.title) ?? text(source.sourceKey) ?? '该法源' }}：缺少必需证据类型 {{ kind }}。</li></template></ul>
    </div>
  </section>
</template>

<style scoped>
.temporal-panel { display: grid; gap: 14px; }
.temporal-paths { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.temporal-path { display: grid; gap: 12px; padding: 14px; border: 1px solid var(--lc-line); border-radius: 10px; background: var(--lc-surface); }
.temporal-path-heading, .temporal-rule-heading { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }
.temporal-path-heading h3 { margin: 0; color: var(--lc-brand-900); font-size: 16px; }
.temporal-path-heading .eyebrow { margin: 0 0 4px; }
.temporal-meta { margin: 0; }
.temporal-sources, .temporal-rules { display: grid; gap: 7px; }
.temporal-sources h4, .temporal-rules h4 { margin: 0; color: var(--lc-brand-900); font-size: 13px; }
.temporal-sources ul, .temporal-blockers ul, .temporal-evidence ul { margin: 0; padding-left: 18px; }
.temporal-sources li { display: flex; flex-wrap: wrap; gap: 6px 10px; color: var(--lc-muted); font-size: 12px; line-height: 1.55; }
.temporal-sources li strong { color: var(--lc-ink); }
.temporal-rule { display: grid; gap: 5px; padding: 9px 10px; border: 1px solid var(--lc-line); border-radius: 7px; }
.temporal-rule-heading { color: var(--lc-muted); font-size: 12px; }
.temporal-outcome, .temporal-numbers, .temporal-selection p { margin: 0; font-size: 13px; line-height: 1.5; }
.temporal-numbers { color: var(--lc-ink); font-weight: 650; }
.temporal-evidence-line { margin: 0; color: #8f1736; font-size: 12px; line-height: 1.5; }
.temporal-blocked { color: #8f1736; background: var(--lc-risk-soft); border-color: var(--lc-risk); }
.temporal-calculated { color: var(--lc-brand-800); background: var(--lc-brand-100); }
.temporal-blockers { margin: 0; display: grid; gap: 6px; }
.temporal-blockers p { margin: 6px 0 0; }
.temporal-selection { margin: 0; display: grid; gap: 3px; }
.temporal-evidence { margin: 0; }
@media (max-width: 720px) { .temporal-paths { grid-template-columns: 1fr; } }
</style>
