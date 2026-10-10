<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ApiError, api, apiV2 } from '../api'
import type { CaseView, SentencingResult } from '../api-types'
import CasePhaseBar from '../components/CasePhaseBar.vue'
import SentencingResultPanel from '../components/SentencingResultPanel.vue'
import LegalTemporalPanel from '../components/LegalTemporalPanel.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { useTaskPolling } from '../composables/useTaskPolling'
import { isPlaceholderCaseId } from '../data/placeholder-cases'
import { rememberT1Case } from '../lib/current-case'
import { toSentencingTaskResult } from '../lib/module-content'
import { toFactsVersionAmounts, toSentencingResultV2 } from '../lib/module-content-v2'

const route = useRoute()
const router = useRouter()
const caseId = computed(() => String(route.params.caseId || ''))
const loading = ref(true)
const error = ref('')
const caseItem = ref<CaseView | null>(null)
const sentencingResult = ref<SentencingResult | null>(null)
const moduleAmounts = ref<SentencingResult['amounts']>([])
const humanReviewRequired = ref(false)
const factsConfirmed = ref<boolean | null>(null)

const creating = ref(false)
const createError = ref('')

const taskId = ref('')
const { task, result, loading: taskLoading, error: taskError, start, stop } = useTaskPolling(() => taskId.value)

const taskTerminal = computed(() => {
  const s = task.value?.status
  return s === 'completed' || s === 'waiting_review' || s === 'failed' || s === 'timed_out' || s === 'rejected'
})
const resultBlocked = computed(() => Boolean(sentencingResult.value?.blockers?.length))
const taskFailed = computed(() => task.value?.status === 'failed' || task.value?.status === 'timed_out')

const workspaceTo = computed(() => (caseItem.value ? `/cases/${caseItem.value.id}` : '/cases'))

async function load() {
  loading.value = true
  error.value = ''
  caseItem.value = null
  sentencingResult.value = null
  moduleAmounts.value = []
  factsConfirmed.value = null
  if (!caseId.value || isPlaceholderCaseId(caseId.value)) {
    loading.value = false
    return
  }
  try {
    caseItem.value = await api.getCase(caseId.value)
    rememberT1Case(caseItem.value.id)
    try {
      // 金额口径读已确认事实快照（定罪/量刑 payload 均不含金额明细）
      const factsHead = await apiV2.getFactsHead(caseId.value)
      const confirmedId = factsHead.confirmedFactsVersionId as string | null
      factsConfirmed.value = Boolean(confirmedId)
      if (confirmedId) {
        const version = await apiV2.getFactsVersion(caseId.value, confirmedId)
        const payload = version.payload
        if (payload && typeof payload === 'object' && !Array.isArray(payload)) {
          moduleAmounts.value = toFactsVersionAmounts(payload as Record<string, unknown>)
        }
      }
    } catch {
      // 事实快照缺失时金额口径留空，不阻塞量刑页
    }
    try {
      const page = await api.listReviews({ module: 'sentencing', archiveStatus: 'open', size: 100 })
      const existing = page.items.find((item) => item.caseId === caseId.value && item.taskId)
      if (existing?.taskId) {
        taskId.value = existing.taskId
        start()
      }
    } catch {
      // 没有已有量刑任务时保持空态，由页面按钮发起
    }
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '案件读取失败。'
  } finally {
    loading.value = false
  }
}

watch(result, (payload) => {
  if (!payload) return
  const content = payload.content
  if (!content || typeof content !== 'object' || Array.isArray(content)) return
  const rec = content as Record<string, unknown>
  const v2 = toSentencingResultV2(rec)
  const normalized = v2 ?? toSentencingTaskResult(rec)
  if (!normalized.amounts?.length && moduleAmounts.value?.length) {
    normalized.amounts = moduleAmounts.value
  }
  sentencingResult.value = normalized
  humanReviewRequired.value = rec.human_review_required === true || rec.humanReviewRequired === true
})

async function runSentencing() {
  if (!caseItem.value || creating.value) return
  creating.value = true
  createError.value = ''
  sentencingResult.value = null
  humanReviewRequired.value = false
  try {
    const created = await apiV2.dispatchModuleExecution(caseItem.value.id, 'sentencing')
    taskId.value = String(created.taskId ?? '')
    start()
  } catch (caught) {
    if (caught instanceof ApiError && caught.status === 501) {
      createError.value = '量刑重放尚未开放。'
    } else if (caught instanceof ApiError && caught.code === 'FACTS_NOT_CONFIRMED') {
      createError.value = '案件事实尚未确认。请回到案件工作区确认事实后再重放宣告口径。'
    } else {
      createError.value = caught instanceof Error ? caught.message : '量刑任务创建失败。'
    }
  } finally {
    creating.value = false
  }
}

function handleLocate() {
  if (caseItem.value) void router.push(`/cases/${caseItem.value.id}`)
}

onMounted(() => void load())
watch(caseId, () => {
  stop()
  taskId.value = ''
  void load()
})
</script>

<template>
  <div class="page-stack">
    <header class="page-heading">
      <div>
        <RouterLink class="back-link" :to="workspaceTo">← 返回案件工作区</RouterLink>
        <p class="eyebrow">量刑推导链</p>
        <h1>量刑分析</h1>
        <p>{{ caseItem?.title || '当前案件' }} · 按已确认事实逐档计算辅助分析参考值并留痕，不输出系统自创结论</p>
      </div>
      <div class="heading-actions">
        <CasePhaseBar current="analysis" />
        <RouterLink class="button button-primary" to="/reviews">提交人工复核</RouterLink>
      </div>
    </header>
    <p class="notice notice-warning" role="note">
      <strong>辅助分析，不替代司法裁量</strong>
      <span>规则计算参考值与罚金为注册表规则的可解释计算结果，输入为已确认事实快照；阻断项只展示待确认，不编造结果。</span>
    </p>
    <div v-if="loading" class="panel empty-state" aria-live="polite">正在读取案件…</div>
    <div v-else-if="error" class="panel">
      <p class="notice notice-error" role="alert">{{ error }}</p>
      <button class="button button-quiet" type="button" @click="load">重试</button>
    </div>
    <template v-else>
      <p v-if="factsConfirmed === false" class="notice notice-warning" role="note">
        <strong>案件事实尚未确认</strong>
        <span>量刑分析以已确认事实快照为输入，请先在案件工作区确认事实，再运行。</span>
        <RouterLink :to="workspaceTo">前往案件工作区</RouterLink>
      </p>
      <section class="panel">
        <div class="panel-heading"><div><p class="section-index">01</p><h2>量刑分析</h2></div></div>
        <p class="panel-note">按已确认事实快照逐档计算量刑区间并留痕；需事实已确认且量刑规则已会签。结果为辅助意见，须人工复核。</p>
        <div class="sentencing-form">
          <button
            class="button button-primary"
            type="button"
            :disabled="creating"
            @click="runSentencing"
          >
            {{ creating ? '派发中…' : '运行量刑分析' }}
          </button>
          <StatusBadge v-if="task" :status="task.status" />
        </div>
        <p v-if="createError" class="notice notice-error" role="alert">{{ createError }}</p>
        <p v-if="taskError" class="notice notice-error" role="alert">{{ taskError }}</p>
        <p v-if="task && !taskTerminal" class="subtle-text">任务 {{ task.id }} · {{ task.currentStage || '排队中' }}…</p>
        <p v-if="taskFailed" class="notice notice-error" role="alert">
          重放失败：{{ task?.error || task?.errorCode || '未知错误' }}
        </p>
        <button v-if="taskFailed" class="button button-quiet" type="button" :disabled="creating" @click="runSentencing">重试</button>
        <p v-if="task && task.status === 'waiting_review'" class="notice notice-info" role="note">
          已核口径已重放，结果待人工复核。<RouterLink to="/reviews">前往复核队列</RouterLink>
        </p>
      </section>

      <section v-if="sentencingResult" class="panel">
        <div class="panel-heading"><div><p class="section-index">02</p><h2>已核对宣告口径</h2></div></div>
        <p v-if="resultBlocked" class="notice notice-warning" role="note">
          <strong>重放被阻断</strong>
          <span>输入未满足已复核口径要求，以下为待确认项，不输出计算参考值。</span>
        </p>
        <SentencingResultPanel :result="sentencingResult" @locate="handleLocate" />
      </section>
      <section v-else-if="taskLoading" class="panel empty-state">正在计算量刑区间…</section>
      <section v-else class="panel empty-state">
        <strong>尚未运行量刑分析</strong>
        <p>按已确认事实快照逐档计算辅助分析参考值；本页不编造结论。</p>
      </section>
      <LegalTemporalPanel v-if="result" :content="result.content" />
    </template>
  </div>
</template>

<style scoped>
.sentencing-form {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 12px;
}
.actor-field {
  display: grid;
  gap: 6px;
  min-width: 220px;
}
.actor-field span {
  color: var(--lc-muted);
  font-size: 12px;
}
.actor-field select {
  padding: 8px 10px;
  border: 1px solid var(--lc-line);
  border-radius: 8px;
  background: var(--lc-surface);
  color: var(--lc-ink);
  font-size: 14px;
}
.subtle-text {
  color: var(--lc-muted);
  font-size: 12px;
}
</style>
