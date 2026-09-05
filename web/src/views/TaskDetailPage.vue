<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import ResultContent from '../components/ResultContent.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { useTaskPolling } from '../composables/useTaskPolling'
import { TASK_STATUS_STAGE } from '../lib/result-content'

const props = defineProps<{ taskId: string }>()
const polling = useTaskPolling(() => props.taskId)
const retryState = ref<'idle' | 'working' | 'done'>('idle')
const retryMessage = ref('')
const showIds = ref(false)
const canRetry = computed(() => Boolean(
  polling.task.value && ['failed', 'timed_out', 'rejected'].includes(polling.task.value.status),
))
const waitingReview = computed(() => polling.task.value?.status === 'waiting_review')
const stages = ['queued', 'running', 'waiting_review', 'completed'] as const

function formatTime(value?: string | null) {
  return value ? new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'medium' }).format(new Date(value)) : '—'
}

function stageClass(status: string, stage: string) {
  const order = ['queued', 'running', 'waiting_review', 'completed']
  const current = ['failed', 'timed_out', 'rejected'].includes(status)
    ? -1
    : Math.max(order.indexOf(status), 0)
  const index = order.indexOf(stage)
  if (status === 'completed' && stage === 'completed') return 'done'
  if (status === 'waiting_review' && stage === 'waiting_review') return 'current'
  if (index < current) return 'done'
  if (index === current) return 'current'
  return ''
}

async function retry() {
  retryState.value = 'working'
  retryMessage.value = ''
  try {
    polling.task.value = await api.retryTask(props.taskId)
    polling.result.value = null
    retryState.value = 'done'
    retryMessage.value = '已创建新的执行记录，旧执行历史仍保留。'
    polling.start()
  } catch (caught) {
    retryState.value = 'idle'
    retryMessage.value = caught instanceof Error ? caught.message : '重试请求失败。'
  }
}

onMounted(polling.start)
watch(() => props.taskId, polling.start)
</script>

<template>
  <div class="page-stack">
    <header class="page-heading compact-heading">
      <div>
        <RouterLink class="back-link" to="/tasks">← 返回执行任务</RouterLink>
        <p class="eyebrow">执行追踪</p>
        <h1>任务执行详情</h1>
        <p class="heading-id">{{ polling.task.value?.caseId || taskId }}</p>
      </div>
      <StatusBadge v-if="polling.task.value" :status="polling.task.value.status" />
    </header>
    <p v-if="polling.error.value" class="notice notice-error" role="alert">
      {{ polling.error.value }}
      <button class="text-button" type="button" @click="polling.refresh">重新读取</button>
    </p>
    <div v-if="polling.loading.value && !polling.task.value" class="panel empty-state" aria-live="polite">正在读取任务状态…</div>
    <template v-if="polling.task.value">
      <ol class="phase-steps" aria-label="执行阶段">
        <li v-for="stage in stages" :key="stage" :class="stageClass(polling.task.value.status, stage)">
          {{ TASK_STATUS_STAGE[stage] }}
        </li>
      </ol>
      <section class="metric-grid" aria-label="任务关键状态">
        <article class="metric-card"><span>当前阶段</span><strong>{{ polling.task.value.currentStage || TASK_STATUS_STAGE[polling.task.value.status] || '等待阶段信息' }}</strong></article>
        <article class="metric-card"><span>结果版本</span><strong>{{ polling.task.value.result ? `v${polling.task.value.result.version}` : '—' }}</strong></article>
        <article class="metric-card"><span>更新时间</span><strong>{{ formatTime(polling.task.value.updatedAt || polling.task.value.createdAt) }}</strong></article>
      </section>
      <section class="detail-grid">
        <article class="panel">
          <div class="panel-heading"><div><p class="section-index">01</p><h2>执行说明</h2></div></div>
          <p v-if="waitingReview" class="notice">结果已生成并等待人工决定。可前往复核队列处理当前版本。</p>
          <div v-if="waitingReview" class="action-box">
            <p>决定只作用于当前不可变结果版本。</p>
            <RouterLink class="button button-primary" to="/reviews">去人工复核</RouterLink>
          </div>
          <button class="text-button" type="button" @click="showIds = !showIds">
            {{ showIds ? '收起技术详情' : '查看技术详情' }}
          </button>
          <dl v-if="showIds" class="data-list">
            <div><dt>Task ID</dt><dd class="mono">{{ polling.task.value.id }}</dd></div>
            <div><dt>Request ID</dt><dd class="mono">{{ polling.task.value.requestId }}</dd></div>
            <div><dt>Execution ID</dt><dd class="mono">{{ polling.task.value.executionId }}</dd></div>
            <div v-if="polling.task.value.caseId"><dt>Case ID</dt><dd class="mono">{{ polling.task.value.caseId }}</dd></div>
            <div><dt>创建时间</dt><dd>{{ formatTime(polling.task.value.createdAt) }}</dd></div>
          </dl>
          <div v-if="polling.task.value.error || polling.task.value.errorCode" class="notice notice-error" role="alert">
            <strong>{{ polling.task.value.errorCode || 'EXECUTION_ERROR' }}</strong>
            <span>{{ polling.task.value.error || '执行未返回更多错误信息。' }}</span>
          </div>
          <div v-if="canRetry" class="action-box">
            <p>重试会创建新的执行，不覆盖本次执行记录。</p>
            <button class="button button-primary" :disabled="retryState === 'working'" type="button" @click="retry">
              {{ retryState === 'working' ? '正在创建…' : '创建重试执行' }}
            </button>
          </div>
          <p v-if="retryMessage" class="notice" :class="retryState === 'done' ? 'notice-success' : 'notice-error'" aria-live="polite">{{ retryMessage }}</p>
        </article>
        <article class="panel result-panel">
          <div class="panel-heading">
            <div><p class="section-index">02</p><h2>结果内容</h2></div>
            <span v-if="polling.result.value" class="subtle-chip">{{ polling.result.value.type }} · v{{ polling.result.value.version }}</span>
          </div>
          <div v-if="polling.resultLoading.value" class="empty-state">正在校验并读取结果…</div>
          <div v-else-if="polling.result.value" class="result-block">
            <div class="result-meta"><span>内容哈希</span><code>{{ polling.result.value.contentHash }}</code></div>
            <ResultContent :content="polling.result.value.content" />
            <p v-if="!polling.task.value.result?.sourceRefs?.length" class="panel-note">本次结果未附带来源引用。</p>
          </div>
          <div v-else-if="polling.task.value.result" class="empty-state">
            <strong>结果内容为空</strong><p>服务端已经返回结果引用，但内容未包含可显示数据。</p>
          </div>
          <div v-else class="empty-state">
            <strong>结果尚未生成</strong><p>排队和执行阶段会自动刷新；终态后停止轮询。</p>
          </div>
        </article>
      </section>
    </template>
  </div>
</template>
