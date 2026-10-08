<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useCaseModule } from '../composables/useCaseModule'
import CandidatePathCard from '../components/CandidatePathCard.vue'
import FactCard from '../components/FactCard.vue'
import RuleResultsPanel from '../components/RuleResultsPanel.vue'
import LegalTemporalPanel from '../components/LegalTemporalPanel.vue'
import {
  APPLICABILITY_LABEL,
  caseRelationsFrom,
  toAnalysisFacts,
  toCandidatePaths,
  toJurisdictionConnections,
  toMissingItems,
} from '../lib/module-content'
import { toV2ModuleAnalysis, v2CandidatePathCards } from '../lib/module-content-v2'
import type { ModuleDispatchOptions } from '../api-types'

const route = useRoute()
const router = useRouter()
const caseId = computed(() => String(route.params.caseId || ''))
const { loading, error, caseItem, moduleState, confirming, confirmError, dispatching, dispatchError, isPlaceholder, load, dispatch, confirm } = useCaseModule(caseId, 'conviction')

const v2Analysis = computed(() => (moduleState.value ? toV2ModuleAnalysis(moduleState.value.content) : null))
const v2PathCards = computed(() => (moduleState.value ? v2CandidatePathCards(moduleState.value.content) : { paths: [], diagnostics: [], present: false }))
const facts = computed(() => (moduleState.value ? toAnalysisFacts(moduleState.value.content) : []))
const paths = computed(() => (moduleState.value ? toCandidatePaths(moduleState.value.content) : []))
const connections = computed(() => (moduleState.value ? toJurisdictionConnections(moduleState.value.content) : []))
const missingItems = computed(() => (moduleState.value ? toMissingItems(moduleState.value.content) : []))
const contentField = (key: string) => {
  const v = moduleState.value?.content?.[key]
  return typeof v === 'string' && v ? v : ''
}
const jurisdictionStatus = computed(() => contentField('jurisdictionStatus') || contentField('jurisdiction_status'))
const legalReviewStatus = computed(() => contentField('legalReviewStatus') || contentField('legal_review_status'))
const jurisdictionSourceIds = computed(() => {
  const raw = moduleState.value?.content?.jurisdictionSourceIds ?? moduleState.value?.content?.jurisdiction_source_ids
  return Array.isArray(raw) ? raw.filter((v): v is string => typeof v === 'string' && v.length > 0) : []
})
const selectedPaths = computed(() => paths.value.filter((p) => p.kind === 'candidate'))
const excludedPaths = computed(() => paths.value.filter((p) => p.kind === 'excluded'))
const subjectiveFacts = computed(() => facts.value.filter((f) => {
  const blob = `${f.id || ''} ${f.stage || ''} ${f.statement || ''}`
  return /knowledge|subjective|明知|认识/i.test(blob)
}))
const actors = computed(() => caseRelationsFrom(caseItem.value).actors ?? [])
const supportingEvidence = computed(() => selectedPaths.value.flatMap((p) => p.supporting || []))
const contraryEvidence = computed(() => selectedPaths.value.flatMap((p) => p.contrary || []).concat(excludedPaths.value.flatMap((p) => p.contrary || [])))
const rawContent = computed(() => (moduleState.value ? JSON.stringify(moduleState.value.content, null, 2) : ''))
const showRaw = ref(false)
const showMissing = ref(false)
const requestedRows = ref<Array<{ requestedCharge: string; chargeKey: string }>>([{ requestedCharge: '', chargeKey: '' }])
const requestedChargesTouched = ref(false)
const requestedChargesLoaded = ref(false)
const requestedCharges = computed(() => requestedRows.value.filter((row) => row.requestedCharge.trim()).map((row) => ({ requestedCharge: row.requestedCharge, chargeKey: row.chargeKey || null })))
const workspaceTo = computed(() => (caseItem.value ? `/cases/${caseItem.value.id}` : '/cases'))
const SEVERITY_LABEL: Record<string, string> = {
  blocking: '阻断',
  warning: '提示',
}

function formatTime(value?: string | null) {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(d)
}

function handleLocate() {
  if (caseItem.value) void router.push(`/cases/${caseItem.value.id}`)
}

function dispatchConviction() {
  const options: ModuleDispatchOptions | undefined = requestedChargesTouched.value || requestedChargesLoaded.value ? { requestedCharges: requestedCharges.value } : undefined
  void dispatch(options)
}

function addRequestedRow() {
  if (requestedRows.value.length < 32) requestedRows.value.push({ requestedCharge: '', chargeKey: '' })
}

function removeRequestedRow(index: number) {
  requestedChargesTouched.value = true
  if (requestedRows.value.length > 1) requestedRows.value.splice(index, 1)
  else requestedRows.value[0] = { requestedCharge: '', chargeKey: '' }
}

function syncRequestedRows(content: Record<string, unknown> | undefined) {
  if (content && Object.prototype.hasOwnProperty.call(content, 'requested_charges') && Array.isArray(content.requested_charges)) {
    const rows = content.requested_charges.flatMap((item) => {
      if (!item || typeof item !== 'object' || Array.isArray(item)) return []
      const record = item as Record<string, unknown>
      return typeof record.requestedCharge === 'string' ? [{ requestedCharge: record.requestedCharge, chargeKey: typeof record.chargeKey === 'string' ? record.chargeKey : '' }] : []
    })
    requestedRows.value = rows.length ? rows : [{ requestedCharge: '', chargeKey: '' }]
    requestedChargesLoaded.value = true
    requestedChargesTouched.value = false
  } else {
    requestedRows.value = [{ requestedCharge: '', chargeKey: '' }]
    requestedChargesLoaded.value = false
    requestedChargesTouched.value = false
  }
}

onMounted(() => void load())
watch(caseId, () => { syncRequestedRows(undefined); void load() })
watch(() => moduleState.value?.content, (content) => syncRequestedRows(content), { immediate: true })
</script>

<template>
  <div class="page-stack">
    <header class="page-heading">
      <div>
        <RouterLink class="back-link" :to="workspaceTo">← 返回案件工作区</RouterLink>
        <p class="eyebrow">模块二 · 定罪研判</p>
        <h1>定罪研判</h1>
        <p>{{ caseItem?.title || '当前案件' }} · 事实结构化、主观认识、罪名界分与法域冲突研判</p>
      </div>
      <div class="heading-actions">
        <span v-if="moduleState" class="subtle-chip">{{ APPLICABILITY_LABEL[moduleState.applicability] }}</span>
        <RouterLink class="button button-primary" to="/reviews">提交人工复核</RouterLink>
      </div>
    </header>

    <p class="notice notice-warning" role="note">
      <strong>辅助研判，不替代司法裁量</strong>
      <span>本页展示法学已核对标注、候选路径及支持/相反证据，所有研判均须由具备资质的人员复核；不自动作出定罪结论。</span>
    </p>

    <div v-if="loading" class="panel empty-state" aria-live="polite">正在读取案件与模块结果…</div>

    <div v-else-if="error" class="panel">
      <p class="notice notice-error" role="alert">{{ error }}</p>
      <button class="button button-quiet" type="button" @click="load">重试</button>
    </div>

    <div v-else-if="isPlaceholder" class="panel empty-state">
      <strong>请先选择真实案件</strong>
      <p>定罪研判挂在具体案件下。请到案件中心新建或选择案件。</p>
      <RouterLink class="button button-primary" to="/cases">前往案件中心</RouterLink>
    </div>

    <template v-else>
      <section class="panel">
        <div class="panel-heading"><div><p class="section-index">01</p><h2>模块状态</h2></div></div>
        <template v-if="moduleState">
          <dl class="data-list inline-data">
            <div><dt>适用性</dt><dd>{{ APPLICABILITY_LABEL[moduleState.applicability] }}</dd></div>
            <div><dt>状态</dt><dd>{{ moduleState.status === 'confirmed' ? '已确认' : '草稿' }}</dd></div>
            <div><dt>版本</dt><dd class="mono">v{{ moduleState.version }}</dd></div>
            <div><dt>事实快照</dt><dd>{{ moduleState.factsStale ? '已过期，需重新确认事实' : '最新' }}</dd></div>
            <div><dt>更新时间</dt><dd>{{ formatTime(moduleState.updatedAt) }}</dd></div>
            <div><dt>来源版本</dt><dd class="mono">{{ moduleState.sourceVersion || '—' }}</dd></div>
          </dl>
          <p v-if="moduleState.factsStale" class="notice notice-warning" role="note">
            <strong>事实快照已过期</strong>
            <span>案件事实已变更，请回到案件工作区重新确认事实后再刷新本模块。</span>
          </p>
          <div class="charge-request-box">
            <label>本次请求核查的罪名或标识（可选）</label>
            <div v-for="(row, index) in requestedRows" :key="index" class="charge-request-row">
              <input v-model="row.requestedCharge" :aria-label="`请求罪名 ${index + 1}`" placeholder="请求罪名原始名称" @input="requestedChargesTouched = true" />
              <input v-model="row.chargeKey" :aria-label="`会签标识 ${index + 1}`" placeholder="已会签标识（可选）" @input="requestedChargesTouched = true" />
              <button class="text-button" type="button" @click="removeRequestedRow(index)">移除</button>
            </div>
            <button v-if="requestedRows.length < 32" class="text-button" type="button" @click="addRequestedRow">增加请求</button>
            <p class="panel-note">名称和标识按原文提交；请按已会签语料精确填写，未覆盖请求会按时点单独列出。</p>
          </div>
        </template>
        <div v-else class="empty-state">
          <strong>该模块尚未产生结果</strong>
          <p>完成案件材料上传与事实确认后，可运行定罪研判（需事实已确认且规则已会签）。</p>
          <div class="charge-request-box">
            <label>本次请求核查的罪名或标识（可选）</label>
            <div v-for="(row, index) in requestedRows" :key="index" class="charge-request-row">
              <input v-model="row.requestedCharge" :aria-label="`请求罪名 ${index + 1}`" placeholder="请求罪名原始名称" @input="requestedChargesTouched = true" />
              <input v-model="row.chargeKey" :aria-label="`会签标识 ${index + 1}`" placeholder="已会签标识（可选）" @input="requestedChargesTouched = true" />
              <button class="text-button" type="button" @click="removeRequestedRow(index)">移除</button>
            </div>
            <button v-if="requestedRows.length < 32" class="text-button" type="button" @click="addRequestedRow">增加请求</button>
            <p class="panel-note">名称和标识按原文提交；请按已会签语料精确填写，未覆盖请求会按时点单独列出。</p>
          </div>
          <button class="button button-primary" type="button" :disabled="dispatching" @click="dispatchConviction">
            {{ dispatching ? '分析中…' : '运行定罪研判' }}
          </button>
          <p v-if="dispatchError" class="notice notice-error" role="alert">{{ dispatchError }}</p>
        </div>
      </section>

      <section v-if="v2Analysis" class="panel">
        <div class="panel-heading"><div><p class="section-index">02</p><h2>规则执行结果</h2></div></div>
        <p class="panel-note">approved 规则包对确认事实快照的逐条求值；不构成定罪结论。</p>
        <RuleResultsPanel :analysis="v2Analysis" />
      </section>

      <section v-if="v2Analysis" class="panel" data-testid="v2-candidate-paths">
        <div class="panel-heading"><div><p class="section-index">03</p><h2>定罪路径研判</h2></div></div>
        <p class="panel-note">分别展示规则执行返回的候选路径；支持与相反证据并列，系统不自动选择路径。</p>
        <div v-if="v2PathCards.diagnostics.length" class="blocker-list">
          <p v-for="diagnostic in v2PathCards.diagnostics" :key="diagnostic.path" class="notice notice-warning" role="alert">
            <strong>路径结果待确认</strong> <span class="mono">{{ diagnostic.path }}</span> {{ diagnostic.message }}
          </p>
        </div>
        <div v-if="v2PathCards.paths.length" class="path-list">
          <CandidatePathCard v-for="p in v2PathCards.paths" :key="p.id ?? p.title" :path="p" @locate="handleLocate" />
        </div>
        <div v-else class="empty-state">
          <strong>{{ v2PathCards.present ? '本次结果尚未返回有效定罪路径' : '本次结果尚未返回定罪路径计划' }}</strong>
          <p>{{ v2PathCards.present ? '路径数据存在格式或核验问题，不能据此作出路径结论。' : '当前仅展示规则执行结果；路径计划尚未生成，不能视为定罪架构已完成。' }}</p>
        </div>
      </section>

      <section v-if="v2Analysis && (v2Analysis.requestedCharges.length || v2Analysis.chargeCoverage.length || v2Analysis.coverageMissingItems.length || v2Analysis.coverageDiagnostics.length)" class="panel" data-testid="charge-coverage">
        <div class="panel-heading"><div><p class="section-index">04</p><h2>请求罪名覆盖</h2></div></div>
        <p class="panel-note">按用户原始请求与法律时点展示已会签规则包覆盖情况，不将未覆盖请求转成候选或近似罪名。</p>
        <div v-if="v2Analysis.coverageDiagnostics.length" class="blocker-list">
          <p v-for="diagnostic in v2Analysis.coverageDiagnostics" :key="diagnostic.path" class="notice notice-warning" role="alert"><strong>覆盖结果待确认</strong> <span class="mono">{{ diagnostic.path }}</span> {{ diagnostic.message }}</p>
        </div>
        <dl v-if="v2Analysis.requestedCharges.length" class="data-list">
          <div v-for="(charge, index) in v2Analysis.requestedCharges" :key="`${charge.requestedCharge}-${index}`"><dt>请求罪名</dt><dd>{{ charge.requestedCharge }}<span v-if="charge.chargeKey" class="mono"> · {{ charge.chargeKey }}</span></dd></div>
        </dl>
        <div v-if="v2Analysis.chargeCoverage.length" class="coverage-list">
          <h3>时点覆盖结果</h3>
          <article v-for="(coverage, index) in v2Analysis.chargeCoverage" :key="`${coverage.requestedCharge}-${coverage.point}-${coverage.date}-${index}`" class="coverage-item">
            <div><strong>{{ coverage.requestedCharge }}</strong><span v-if="coverage.chargeKey" class="mono"> · {{ coverage.chargeKey }}</span></div>
            <div class="coverage-meta">{{ coverage.point }} · {{ coverage.date }} · {{ coverage.covered ? '已覆盖' : '未覆盖' }}</div>
            <p v-if="coverage.ruleVersions.length" class="coverage-sources">规则：{{ coverage.ruleVersions.map((rule) => `${rule.ruleId}@${rule.ruleVersion}`).join('、') }}；法源：{{ coverage.ruleVersions.flatMap((rule) => rule.sourceIds).join('、') || '—' }}</p>
            <p v-else class="coverage-sources">未返回可用规则版本。</p>
          </article>
        </div>
        <ul v-if="v2Analysis.coverageMissingItems.length" class="missing-list">
          <li v-for="item in v2Analysis.coverageMissingItems" :key="item.id"><span class="subtle-chip">未覆盖</span>{{ item.requestedCharge ?? '未提供请求名称（计划项）' }}<span v-if="item.chargeKey" class="mono">（{{ item.chargeKey }}）</span> · {{ item.point }} · {{ item.date }}：{{ item.reason }}</li>
        </ul>
        <p v-else-if="v2Analysis.requestedCharges.length" class="panel-note">请求罪名均返回覆盖结果。</p>
      </section>

      <template v-if="!v2Analysis">
      <section class="panel">
        <div class="panel-heading"><div><p class="section-index">02</p><h2>案件事实结构化整理</h2></div></div>
        <p class="panel-note">按「人—行为—阶段」整理法学已核对标注，同一行为人不同阶段分列，不合并；定位指向本次上传材料。</p>
        <div v-if="facts.length" class="fact-list">
          <FactCard v-for="f in facts" :key="f.id ?? f.statement" :fact="f" @locate="handleLocate" />
        </div>
        <dl v-else-if="actors.length" class="data-list">
          <div v-for="actor in actors" :key="actor.actorId">
            <dt>行为人</dt>
            <dd>{{ actor.label || actor.actorId }}<template v-if="actor.roleHint"> · {{ actor.roleHint }}</template></dd>
          </div>
        </dl>
        <div v-else class="empty-state">
          <strong>本案尚未登记结构化事实</strong>
          <p>请先在案件工作区确认事实。</p>
        </div>
      </section>

      <section class="panel">
        <div class="panel-heading"><div><p class="section-index">03</p><h2>罪名界分研判</h2></div></div>
        <p class="panel-note">围绕诈骗共犯、帮信、掩隐的界分，逐项审查主观认识、协作关系、行为对象与金额口径。支持证据与相反证据并列展示。</p>
        <div v-if="paths.length" class="path-list">
          <CandidatePathCard v-for="p in paths" :key="p.id ?? p.title" :path="p" @locate="handleLocate" />
        </div>
        <div v-else class="empty-state">
          <strong>本案尚未登记候选路径</strong>
          <p>确认事实后，候选与排除路径会出现在这里。</p>
        </div>
      </section>

      <section class="panel">
        <div class="panel-heading"><div><p class="section-index">04</p><h2>主观认识与证据支撑分析</h2></div></div>
        <dl class="data-list">
          <div>
            <dt>认识内容</dt>
            <dd v-if="subjectiveFacts.length">{{ subjectiveFacts.map((f) => f.statement).join('；') }}</dd>
            <dd v-else>本案未单独登记主观认识条目，见上方事实与候选路径。</dd>
          </div>
          <div>
            <dt>形成阶段</dt>
            <dd v-if="subjectiveFacts.some((f) => f.stage)">{{ subjectiveFacts.map((f) => f.stage).filter(Boolean).join('；') }}</dd>
            <dd v-else>—</dd>
          </div>
          <div>
            <dt>支持证据</dt>
            <dd v-if="supportingEvidence.length" class="mono">{{ supportingEvidence.map((e) => e.id || e.quote || e.locator).filter(Boolean).join('、') }}</dd>
            <dd v-else>—</dd>
          </div>
          <div>
            <dt>相反证据</dt>
            <dd v-if="contraryEvidence.length" class="mono">{{ contraryEvidence.map((e) => e.id || e.quote || e.locator).filter(Boolean).join('、') }}</dd>
            <dd v-else>—</dd>
          </div>
          <div>
            <dt>缺失事实</dt>
            <dd v-if="missingItems.length">{{ missingItems.length }} 条，见下方待确认事项</dd>
            <dd v-else>无额外缺失事项</dd>
          </div>
        </dl>
      </section>

      <section class="panel">
        <div class="panel-heading"><div><p class="section-index">05</p><h2>法域冲突研判</h2></div></div>
        <dl class="data-list">
          <div><dt>管辖识别</dt><dd><span v-if="jurisdictionStatus" class="mono">{{ jurisdictionStatus }}</span><span v-else>—</span></dd></div>
          <div><dt>管辖法源</dt><dd><span v-if="jurisdictionSourceIds.length" class="mono">{{ jurisdictionSourceIds.join('、') }}</span><span v-else>—</span></dd></div>
        </dl>
        <div v-if="connections.length" class="connection-list">
          <p class="panel-note">管辖连接点（已复核数据原样展示，含域外连接点专用核验状态）</p>
          <dl class="data-list">
            <div v-for="(c, i) in connections" :key="c.connectionId ?? i">
              <dt class="mono">{{ c.type || '连接点' }}</dt>
              <dd>
                {{ c.value }}
                <span v-if="c.status" class="subtle-chip mono">{{ c.status }}</span>
              </dd>
            </div>
          </dl>
        </div>
      </section>

      <section class="panel">
        <div class="panel-heading"><div><p class="section-index">06</p><h2>基准位置与待确认事项</h2></div></div>
        <p class="panel-note">以下为已核对标注中的基准位置与缺失事实原样展示，不构成定罪结论。</p>
        <dl class="data-list">
          <div>
            <dt>基准路径（selected）</dt>
            <dd v-if="selectedPaths.length">{{ selectedPaths.map((p) => p.title).join('；') }}</dd>
            <dd v-else>未登记基准路径</dd>
          </div>
          <div>
            <dt>排除路径（excluded）</dt>
            <dd v-if="excludedPaths.length">{{ excludedPaths.map((p) => p.title).join('；') }}</dd>
            <dd v-else>未登记排除路径</dd>
          </div>
          <div>
            <dt>法学复核状态</dt>
            <dd><span v-if="legalReviewStatus" class="mono">{{ legalReviewStatus }}</span><span v-else>—</span></dd>
          </div>
        </dl>
        <div v-if="missingItems.length" class="missing-fold">
          <button class="text-button" type="button" @click="showMissing = !showMissing">
            {{ showMissing ? '收起待确认事项' : `待确认事项 ${missingItems.length} 条` }}
          </button>
          <ul v-if="showMissing" class="missing-list">
            <li v-for="(m, i) in missingItems" :key="m.id ?? i">
              <span v-if="m.severity" class="subtle-chip">{{ SEVERITY_LABEL[m.severity] || m.severity }}</span>
              {{ m.description }}
            </li>
          </ul>
        </div>
        <p v-else class="panel-note">待确认事项：无</p>
      </section>
      </template>

      <LegalTemporalPanel v-if="moduleState" :content="moduleState.content" />

      <section v-if="moduleState" class="panel">
        <div class="panel-heading">
          <div><p class="section-index">07</p><h2>结果内容（原始）</h2></div>
          <button class="text-button" type="button" @click="showRaw = !showRaw">{{ showRaw ? '收起' : '查看' }}</button>
        </div>
        <p class="panel-note">模块内容按已登记字段展示，便于核对结构。</p>
        <pre v-if="showRaw" class="raw-payload">{{ rawContent }}</pre>
      </section>

      <div v-if="moduleState" class="action-box">
        <p>{{ moduleState.status === 'confirmed' ? '该模块结果已经人工复核确认。' : '核对候选路径与证据后提交人工复核。' }}</p>
        <button class="button button-quiet" type="button" :disabled="dispatching" @click="dispatchConviction">
          {{ dispatching ? '分析中…' : '重新分析' }}
        </button>
        <button
          class="button button-primary"
          type="button"
          :disabled="confirming || moduleState.status === 'confirmed'"
          @click="confirm"
        >
          {{ confirming ? '提交中…' : moduleState.status === 'confirmed' ? '已确认' : '提交人工复核' }}
        </button>
      </div>
      <p v-if="confirmError" class="notice notice-error" role="alert">{{ confirmError }}</p>
      <p v-if="dispatchError" class="notice notice-error" role="alert">{{ dispatchError }}</p>
    </template>
  </div>
</template>

<style scoped>
.fact-list, .path-list {
  display: grid;
  gap: 10px;
}
.charge-request-box {
  display: grid;
  gap: 8px;
  margin-top: 14px;
  max-width: 720px;
}
.charge-request-box label { font-weight: 600; font-size: 13px; }
.charge-request-box textarea {
  width: 100%;
  resize: vertical;
  padding: 10px;
  border: 1px solid var(--lc-line);
  border-radius: 6px;
  background: var(--lc-surface);
  color: var(--lc-ink);
  font: inherit;
}
.coverage-list { display: grid; gap: 10px; margin-top: 14px; }
.coverage-list h3 { margin: 0; font-size: 14px; }
.coverage-item { display: grid; gap: 5px; padding: 10px 12px; border: 1px solid var(--lc-line); border-radius: 6px; background: var(--lc-surface-alt); }
.coverage-item p { margin: 0; }
.coverage-meta, .coverage-sources { color: var(--lc-muted); font-size: 12px; }
.missing-fold { display: grid; gap: 10px; margin-top: 12px; }
.missing-list {
  margin: 0;
  padding-left: 18px;
  display: grid;
  gap: 10px;
  color: var(--lc-muted);
  font-size: 13px;
  line-height: 1.6;
}
.missing-list .subtle-chip { margin-right: 8px; }
</style>
