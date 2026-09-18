<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useCaseModule } from '../composables/useCaseModule'
import CandidatePathCard from '../components/CandidatePathCard.vue'
import FactCard from '../components/FactCard.vue'
import {
  APPLICABILITY_LABEL,
  toAnalysisFacts,
  toCandidatePaths,
  toJurisdictionConnections,
  toMissingItems,
} from '../lib/module-content'

const route = useRoute()
const router = useRouter()
const caseId = computed(() => String(route.params.caseId || ''))
const { loading, error, caseItem, moduleState, confirming, confirmError, isPlaceholder, load, confirm } = useCaseModule(caseId, 'conviction')

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
const rawContent = computed(() => (moduleState.value ? JSON.stringify(moduleState.value.content, null, 2) : ''))
const showRaw = ref(false)
const workspaceTo = computed(() => (caseItem.value ? `/cases/${caseItem.value.id}` : '/cases'))

function formatTime(value?: string | null) {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(d)
}

function handleLocate() {
  if (caseItem.value) void router.push(`/cases/${caseItem.value.id}`)
}

onMounted(() => void load())
watch(caseId, () => void load())
</script>

<template>
  <div class="page-stack">
    <header class="page-heading">
      <div>
        <RouterLink class="back-link" :to="workspaceTo">← 返回案件工作区</RouterLink>
        <p class="eyebrow">模块二 · 定罪研判</p>
        <h1>定罪研判</h1>
        <p>{{ caseItem?.title || '未接通案件' }} · 事实结构化、主观认识、罪名界分与法域冲突研判</p>
      </div>
      <div class="heading-actions">
        <span v-if="moduleState" class="subtle-chip">{{ APPLICABILITY_LABEL[moduleState.applicability] }}</span>
        <RouterLink class="button button-primary" to="/reviews">提交人工复核</RouterLink>
      </div>
    </header>

    <p class="notice notice-warning" role="note">
      <strong>辅助分析，不替代专业判断</strong>
      <span>本页只展示候选路径与支持/相反证据，支持人工修正全部研判结论；不在前端计算罪名或撰写判断理由。</span>
    </p>

    <div v-if="loading" class="panel empty-state" aria-live="polite">正在读取案件与模块结果…</div>

    <div v-else-if="error" class="panel">
      <p class="notice notice-error" role="alert">{{ error }}</p>
      <button class="button button-quiet" type="button" @click="load">重试</button>
    </div>

    <div v-else-if="isPlaceholder" class="panel empty-state">
      <strong>请先选择真实案件</strong>
      <p>定罪研判挂在具体案件下，示例案件不适用。请到案件中心新建或选择案件。</p>
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
        </template>
        <div v-else class="empty-state">
          <strong>该模块尚未产生结果</strong>
          <p>完成案件材料上传与事实确认后，由引擎生成定罪研判。</p>
        </div>
      </section>

      <section class="panel">
        <div class="panel-heading"><div><p class="section-index">02</p><h2>案件事实结构化整理</h2></div></div>
        <p class="panel-note">按「人—行为—阶段」整理事实，同一行为人不同阶段分列，不合并。</p>
        <div v-if="facts.length" class="fact-list">
          <FactCard v-for="f in facts" :key="f.id ?? f.statement" :fact="f" @locate="handleLocate" />
        </div>
        <dl v-else class="data-list">
          <div><dt>行为人</dt><dd class="placeholder-text">待引擎输出</dd></div>
          <div><dt>行为类型</dt><dd class="placeholder-text">待引擎输出</dd></div>
          <div><dt>参与期间</dt><dd class="placeholder-text">待引擎输出</dd></div>
          <div><dt>控制账户 / 设备</dt><dd class="placeholder-text">待引擎输出</dd></div>
          <div><dt>指令关系</dt><dd class="placeholder-text">待引擎输出</dd></div>
        </dl>
      </section>

      <section class="panel">
        <div class="panel-heading"><div><p class="section-index">03</p><h2>罪名界分研判</h2></div></div>
        <p class="panel-note">围绕诈骗共犯、帮信、掩隐的界分，逐项审查主观认识、协作关系、行为对象与金额口径。支持证据与相反证据并列展示。</p>
        <div v-if="paths.length" class="path-list">
          <CandidatePathCard v-for="p in paths" :key="p.id ?? p.title" :path="p" @locate="handleLocate" />
        </div>
        <dl v-else class="data-list">
          <div><dt>诈骗共同犯罪</dt><dd class="placeholder-text">待引擎输出</dd></div>
          <div><dt>帮助信息网络犯罪活动</dt><dd class="placeholder-text">待引擎输出</dd></div>
          <div><dt>掩饰隐瞒犯罪所得</dt><dd class="placeholder-text">待引擎输出</dd></div>
        </dl>
      </section>

      <section class="panel">
        <div class="panel-heading"><div><p class="section-index">04</p><h2>主观认识与证据支撑分析</h2></div></div>
        <dl class="data-list">
          <div><dt>认识内容</dt><dd class="placeholder-text">待引擎输出</dd></div>
          <div><dt>形成时间</dt><dd class="placeholder-text">待引擎输出</dd></div>
          <div><dt>支持证据</dt><dd class="placeholder-text">待引擎输出</dd></div>
          <div><dt>相反证据</dt><dd class="placeholder-text">待引擎输出</dd></div>
          <div><dt>缺失事实</dt><dd class="placeholder-text">待引擎输出</dd></div>
        </dl>
      </section>

      <section class="panel">
        <div class="panel-heading"><div><p class="section-index">05</p><h2>法域冲突研判</h2></div></div>
        <dl class="data-list">
          <div><dt>管辖识别</dt><dd><span v-if="jurisdictionStatus" class="mono">{{ jurisdictionStatus }}</span><span v-else class="placeholder-text">待引擎输出</span></dd></div>
          <div><dt>管辖法源</dt><dd><span v-if="jurisdictionSourceIds.length" class="mono">{{ jurisdictionSourceIds.join('、') }}</span><span v-else class="placeholder-text">待引擎输出</span></dd></div>
          <div><dt>中外罪名对照</dt><dd class="placeholder-text">待引擎输出</dd></div>
          <div><dt>法律光谱定位</dt><dd class="placeholder-text">民事 / 行政 / 刑事边界 —— 待引擎输出</dd></div>
          <div><dt>双重追责风险</dt><dd class="placeholder-text">待引擎输出</dd></div>
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
        <p class="panel-note">以下为已复核数据中的基准位置（baseline_position）与缺失事实原样展示，不构成定罪结论。</p>
        <dl class="data-list">
          <div>
            <dt>基准路径（selected）</dt>
            <dd v-if="selectedPaths.length">{{ selectedPaths.map((p) => p.title).join('；') }}</dd>
            <dd v-else class="placeholder-text">待引擎输出</dd>
          </div>
          <div>
            <dt>排除路径（excluded）</dt>
            <dd v-if="excludedPaths.length">{{ excludedPaths.map((p) => p.title).join('；') }}</dd>
            <dd v-else class="placeholder-text">待引擎输出</dd>
          </div>
          <div>
            <dt>法学复核状态</dt>
            <dd><span v-if="legalReviewStatus" class="mono">{{ legalReviewStatus }}</span><span v-else class="placeholder-text">待引擎输出</span></dd>
          </div>
        </dl>
        <div v-if="missingItems.length" class="missing-list">
          <p class="panel-note">缺失事实 / 待确认事项（按已复核数据原样展示，不推断结论）</p>
          <ul>
            <li v-for="(m, i) in missingItems" :key="m.id ?? i">
              <span v-if="m.severity" class="subtle-chip mono">{{ m.severity }}</span>
              {{ m.description }}
            </li>
          </ul>
        </div>
        <p v-else class="panel-note">缺失事实 / 待确认事项：<span class="placeholder-text">待引擎输出</span></p>
      </section>

      <section v-if="moduleState" class="panel">
        <div class="panel-heading">
          <div><p class="section-index">07</p><h2>结果内容（原始）</h2></div>
          <button class="text-button" type="button" @click="showRaw = !showRaw">{{ showRaw ? '收起' : '查看' }}</button>
        </div>
        <p class="panel-note">T3 精确 key 尚未会签，暂以原始载荷展示，便于核对字段结构。</p>
        <pre v-if="showRaw" class="raw-payload">{{ rawContent }}</pre>
      </section>

      <div v-if="moduleState" class="action-box">
        <p>{{ moduleState.status === 'confirmed' ? '该模块结果已确认，可提交人工复核。' : '核对候选路径与证据后确认本模块结果。' }}</p>
        <button
          class="button button-primary"
          type="button"
          :disabled="confirming || moduleState.status === 'confirmed'"
          @click="confirm"
        >
          {{ confirming ? '确认中…' : moduleState.status === 'confirmed' ? '已确认' : '确认模块结果' }}
        </button>
      </div>
      <p v-if="confirmError" class="notice notice-error" role="alert">{{ confirmError }}</p>
    </template>
  </div>
</template>

<style scoped>
.placeholder-text { color: var(--lc-muted); }
.fact-list, .path-list {
  display: grid;
  gap: 10px;
}
</style>
