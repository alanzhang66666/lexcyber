<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ApiError, api } from '../api'
import type { CaseView, RelationActor, SentencingResult } from '../api-types'
import CasePhaseBar from '../components/CasePhaseBar.vue'
import SentencingResultPanel from '../components/SentencingResultPanel.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { useTaskPolling } from '../composables/useTaskPolling'
import { isPlaceholderCaseId } from '../data/placeholder-cases'
import { rememberT1Case } from '../lib/current-case'
import { toAmounts, toSentencingTaskResult } from '../lib/module-content'

const route = useRoute()
const router = useRouter()
const caseId = computed(() => String(route.params.caseId || ''))
const loading = ref(true)
const error = ref('')
const caseItem = ref<CaseView | null>(null)
const sentencingResult = ref<SentencingResult | null>(null)
const moduleAmounts = ref<SentencingResult['amounts']>([])
const analysisStatus = ref('')
const humanReviewRequired = ref(false)

const actors = computed<RelationActor[]>(() => {
  const metadata = caseItem.value?.metadata
  if (!metadata || typeof metadata !== 'object' || Array.isArray(metadata)) return []
  const relations = (metadata as Record<string, unknown>).relations
  if (!relations || typeof relations !== 'object' || Array.isArray(relations)) return []
  const list = (relations as Record<string, unknown>).actors
  return Array.isArray(list) ? (list as RelationActor[]) : []
})
const datasetCaseId = computed(() => {
  const metadata = caseItem.value?.metadata
  if (!metadata || typeof metadata !== 'object' || Array.isArray(metadata)) return ''
  const v = (metadata as Record<string, unknown>).datasetCaseId
  return typeof v === 'string' ? v : ''
})
const selectedActorId = ref('')
const creating = ref(false)
const createError = ref('')

const taskId = ref('')
const { task, result, loading: taskLoading, error: taskError, start, stop } = useTaskPolling(() => taskId.value)

const taskTerminal = computed(() => {
  const s = task.value?.status
  return s === 'completed' || s === 'waiting_review' || s === 'failed' || s === 'timed_out' || s === 'rejected'
})
const resultBlocked = computed(() => Boolean(sentencingResult.value?.blockers?.length))

const workspaceTo = computed(() => (caseItem.value ? `/cases/${caseItem.value.id}` : '/cases'))

function actorLabel(actorId: string) {
  return actors.value.find((a) => a.actorId === actorId)?.label || actorId
}

async function load() {
  loading.value = true
  error.value = ''
  caseItem.value = null
  sentencingResult.value = null
  moduleAmounts.value = []
  if (!caseId.value || isPlaceholderCaseId(caseId.value)) {
    loading.value = false
    return
  }
  try {
    caseItem.value = await api.getCase(caseId.value)
    rememberT1Case(caseItem.value.id)
    if (!selectedActorId.value && actors.value.length) {
      selectedActorId.value = actors.value[0].actorId
    }
    try {
      const moduleState = await api.getCaseModule(caseId.value, 'conviction')
      if (moduleState.content && typeof moduleState.content === 'object') {
        moduleAmounts.value = toAmounts(moduleState.content as Record<string, unknown>)
      }
    } catch {
      // 定罪模块结果缺失时金额口径留空，不阻塞量刑页
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
  const normalized = toSentencingTaskResult(rec)
  if (!normalized.amounts?.length && moduleAmounts.value?.length) {
    normalized.amounts = moduleAmounts.value
  }
  sentencingResult.value = normalized
  analysisStatus.value = typeof rec.analysisStatus === 'string' ? rec.analysisStatus : ''
  humanReviewRequired.value = rec.humanReviewRequired === true
})

async function runSentencing() {
  if (!caseItem.value || creating.value) return
  creating.value = true
  createError.value = ''
  sentencingResult.value = null
  analysisStatus.value = ''
  humanReviewRequired.value = false
  try {
    const created = await api.createTask({
      query: `量刑重放：${caseItem.value.title} / ${actorLabel(selectedActorId.value)}`,
      caseId: caseItem.value.id,
      metadata: {
        taskType: 'sentencing.calculate',
        sentencing: {
          datasetCaseId: datasetCaseId.value,
          actorId: selectedActorId.value,
        },
      },
    })
    taskId.value = created.id
    start()
  } catch (caught) {
    if (caught instanceof ApiError && caught.status === 501) {
      createError.value = '当前演示未开放量刑重放。'
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
  selectedActorId.value = ''
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
        <p>{{ caseItem?.title || '当前案件' }} · 重放法学负责人已复核的宣告口径，不输出系统自创刑期</p>
      </div>
      <div class="heading-actions">
        <CasePhaseBar current="analysis" />
        <RouterLink class="button button-primary" to="/reviews">提交人工复核</RouterLink>
      </div>
    </header>
    <p class="notice notice-warning" role="note">
      <strong>辅助分析，不替代司法裁量</strong>
      <span>刑期与罚金为已复核宣告口径的留痕重放，计算参数必须全部经人工确认；阻断项只展示待确认，不编造结果。</span>
    </p>
    <div v-if="loading" class="panel empty-state" aria-live="polite">正在读取案件…</div>
    <div v-else-if="error" class="panel">
      <p class="notice notice-error" role="alert">{{ error }}</p>
      <button class="button button-quiet" type="button" @click="load">重试</button>
    </div>
    <template v-else>
      <section class="panel">
        <div class="panel-heading"><div><p class="section-index">01</p><h2>重放输入</h2></div></div>
        <p class="panel-note">按行为主体分别重放法学已核对的宣告口径。无已核口径的主体会列出待确认项，不编造刑期。</p>
        <div class="sentencing-form">
          <label class="actor-field">
            <span>行为主体</span>
            <select v-model="selectedActorId" :disabled="!actors.length">
              <option v-for="a in actors" :key="a.actorId" :value="a.actorId">{{ a.label || a.actorId }}</option>
            </select>
          </label>
          <button
            class="button button-primary"
            type="button"
            :disabled="creating || !selectedActorId || !datasetCaseId"
            @click="runSentencing"
          >
            {{ creating ? '创建中…' : '重放已核对宣告口径' }}
          </button>
          <StatusBadge v-if="task" :status="task.status" />
        </div>
        <p v-if="!actors.length || !datasetCaseId" class="notice notice-info" role="note">
          本案尚未绑定已核对主体，无法重放宣告口径。
        </p>
        <p v-if="createError" class="notice notice-error" role="alert">{{ createError }}</p>
        <p v-if="taskError" class="notice notice-error" role="alert">{{ taskError }}</p>
        <p v-if="task && !taskTerminal" class="subtle-text">任务 {{ task.id }} · {{ task.currentStage || '排队中' }}…</p>
        <p v-if="task && task.status === 'failed'" class="notice notice-error" role="alert">
          重放失败：{{ task.error || task.errorCode || '未知错误' }}
        </p>
        <p v-if="task && task.status === 'waiting_review'" class="notice notice-info" role="note">
          已核口径已重放，结果待人工复核。<RouterLink to="/reviews">前往复核队列</RouterLink>
        </p>
      </section>

      <section v-if="sentencingResult" class="panel">
        <div class="panel-heading"><div><p class="section-index">02</p><h2>已核对宣告口径</h2></div></div>
        <p v-if="analysisStatus === 'blocked'" class="notice notice-warning" role="note">
          <strong>重放被阻断</strong>
          <span>输入未满足已复核口径要求，以下为待确认项，不输出刑期。</span>
        </p>
        <SentencingResultPanel :result="sentencingResult" @locate="handleLocate" />
      </section>
      <section v-else-if="taskLoading" class="panel empty-state">正在重放已核对口径…</section>
      <section v-else class="panel empty-state">
        <strong>尚未重放宣告口径</strong>
        <p>选择行为主体后重放法学已核对的宣告口径；本页不计算刑期。</p>
      </section>
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
