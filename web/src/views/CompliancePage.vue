<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useCaseModule } from '../composables/useCaseModule'
import FactCard from '../components/FactCard.vue'
import { APPLICABILITY_LABEL, caseRelationsFrom, toAnalysisFacts, toComplianceChecklist } from '../lib/module-content'

const route = useRoute()
const router = useRouter()
const caseId = computed(() => String(route.params.caseId || ''))
const { loading, error, caseItem, moduleState, confirming, confirmError, dispatching, dispatchError, isPlaceholder, load, dispatch, confirm } = useCaseModule(caseId, 'compliance')

const facts = computed(() => (moduleState.value ? toAnalysisFacts(moduleState.value.content) : []))
const checklist = computed(() => (moduleState.value ? toComplianceChecklist(moduleState.value.content) : []))
const contentNote = computed(() => {
  const note = moduleState.value?.content?.note
  return typeof note === 'string' && note.trim() ? note : ''
})
const rawContent = computed(() => (moduleState.value ? JSON.stringify(moduleState.value.content, null, 2) : ''))
const showRaw = ref(false)
const workspaceTo = computed(() => (caseItem.value ? `/cases/${caseItem.value.id}` : '/cases'))
const events = computed(() => caseRelationsFrom(caseItem.value).events ?? [])

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
        <p class="eyebrow">模块一 · 合规筛查</p>
        <h1>合规筛查</h1>
        <p>{{ caseItem?.title || '当前案件' }} · 整理合规事实与风险时间线</p>
      </div>
      <div class="heading-actions">
        <span v-if="moduleState" class="subtle-chip">{{ APPLICABILITY_LABEL[moduleState.applicability] }}</span>
        <RouterLink class="button button-primary" to="/reviews">提交人工复核</RouterLink>
      </div>
    </header>

    <p class="notice notice-warning" role="note">
      <strong>辅助分析，不替代专业判断</strong>
      <span>本页展示法学已核对标注中的合规事实与来源，定位指向本次上传材料；不在前端计算合规结论或风险分数。</span>
    </p>

    <div v-if="loading" class="panel empty-state" aria-live="polite">正在读取案件与模块结果…</div>

    <div v-else-if="error" class="panel">
      <p class="notice notice-error" role="alert">{{ error }}</p>
      <button class="button button-quiet" type="button" @click="load">重试</button>
    </div>

    <div v-else-if="isPlaceholder" class="panel empty-state">
      <strong>请先选择真实案件</strong>
      <p>合规筛查挂在具体案件下。请到案件中心新建或选择案件。</p>
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
          <p>完成案件材料上传与事实确认后，可运行合规梳理（需事实已确认且规则已会签）。</p>
          <button class="button button-primary" type="button" :disabled="dispatching" @click="dispatch">
            {{ dispatching ? '分析中…' : '运行合规梳理' }}
          </button>
          <p v-if="dispatchError" class="notice notice-error" role="alert">{{ dispatchError }}</p>
        </div>
      </section>

      <section class="panel">
        <div class="panel-heading"><div><p class="section-index">02</p><h2>合规事实梳理</h2></div></div>
        <p class="panel-note">按以下维度整理客观事实，作为行为归属与主观认识的审查底稿；条目来自法学已核对标注，不是系统合规结论。</p>
        <p v-if="contentNote" class="notice notice-info" role="note">{{ contentNote }}</p>
        <div v-if="checklist.length" class="checklist">
          <div v-for="(c, i) in checklist" :key="c.category ?? i" class="checklist-item">
            <span class="checklist-category">{{ c.category }}</span>
            <span class="checklist-status" title="状态为 T3 字段原文，待法核">{{ c.status || '待法核' }}</span>
            <span v-if="c.evidenceIds?.length" class="checklist-evidence">{{ c.evidenceIds.length }} 项证据</span>
          </div>
        </div>
        <div v-else-if="facts.length" class="fact-list">
          <FactCard v-for="f in facts" :key="f.id ?? f.statement" :fact="f" @locate="handleLocate" />
        </div>
        <div v-else class="empty-state">
          <strong>本案没有单独的合规清单</strong>
          <p>{{ moduleState?.applicability === 'not_applicable' ? '模块已标明不适用。' : '已确认事实见上方面板；未登记制度/岗位等分项。' }}</p>
        </div>
      </section>

      <section class="panel">
        <div class="panel-heading"><div><p class="section-index">03</p><h2>合规与风险时间线</h2></div></div>
        <p class="panel-note">按时间顺序排列合规相关事实，标注发生时间、内容、材料来源与整理维度。</p>
        <dl v-if="events.length" class="data-list">
          <div v-for="event in events" :key="event.eventId">
            <dt class="mono">{{ event.occurredOn || event.stage || event.eventId }}</dt>
            <dd>{{ event.stage || '事件' }}<template v-if="event.actorId"> · {{ event.actorId }}</template><template v-if="event.locator"> · {{ event.locator }}</template></dd>
          </div>
        </dl>
        <div v-else class="empty-state">
          <strong>本案未登记合规时间线</strong>
          <p>事件时间线可在案件工作区查看。</p>
        </div>
      </section>

      <section v-if="moduleState" class="panel">
        <div class="panel-heading">
          <div><p class="section-index">04</p><h2>结果内容（原始）</h2></div>
          <button class="text-button" type="button" @click="showRaw = !showRaw">{{ showRaw ? '收起' : '查看' }}</button>
        </div>
        <p class="panel-note">模块内容按已登记字段展示，便于核对结构。</p>
        <pre v-if="showRaw" class="raw-payload">{{ rawContent }}</pre>
      </section>

      <div v-if="moduleState" class="action-box">
        <p>{{ moduleState.status === 'confirmed' ? '该模块结果已经人工复核确认。' : '核对事实与来源后提交人工复核。' }}</p>
        <button class="button button-quiet" type="button" :disabled="dispatching" @click="dispatch">
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
.fact-list {
  display: grid;
  gap: 10px;
}
.checklist {
  display: grid;
  gap: 8px;
}
.checklist-item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  background: var(--lc-surface);
  border: 1px solid var(--lc-line);
  border-radius: 8px;
}
.checklist-category {
  color: var(--lc-ink);
  font-size: 13px;
  font-weight: 600;
}
.checklist-status {
  padding: 2px 10px;
  color: var(--lc-brand-800);
  background: var(--lc-brand-100);
  border-radius: 999px;
  font-size: 11px;
  font-weight: 750;
}
.checklist-evidence {
  margin-left: auto;
  color: var(--lc-muted);
  font-size: 12px;
}
</style>
