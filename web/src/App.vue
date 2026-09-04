<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import type { ResultPayload, ReviewRecord as Review, TaskStatus, TaskView } from './api-types'

const query = ref('Summarize this generic workflow input')
const metadataText = ref('{"source":"demo"}')
const requireReview = ref(false)
const currentTask = ref<TaskView | null>(null)
const resultContent = ref<ResultPayload | null>(null)
const reviews = ref<Review[]>([])
const error = ref('')
const loading = ref(false)
let pollTimer: number | undefined

const statusLabels: Record<TaskStatus, string> = {
  queued: '排队中', running: '执行中', completed: '已完成', waiting_review: '等待复核',
  failed: '失败', timed_out: '超时', rejected: '已拒绝',
}
const statusLabel = computed(() => currentTask.value ? statusLabels[currentTask.value.status] : '未提交')
const terminal = (status?: TaskStatus) => Boolean(status && ['completed', 'failed', 'timed_out', 'rejected'].includes(status))

async function readJson(response: Response) {
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload.message || payload.detail || `请求失败 (${response.status})`)
  return payload
}

async function submitTask() {
  error.value = ''
  loading.value = true
  try {
    const metadata = JSON.parse(metadataText.value || '{}') as Record<string, unknown>
    if (requireReview.value) metadata.demo_requires_review = true
    const response = await fetch('/v1/tasks', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: query.value, metadata }),
    })
    currentTask.value = await readJson(response) as TaskView
    resultContent.value = null
    startPolling()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '提交失败'
  } finally {
    loading.value = false
  }
}

function startPolling() {
  if (pollTimer !== undefined) window.clearInterval(pollTimer)
  pollTimer = window.setInterval(refreshTask, 1500)
  void refreshTask()
}

async function refreshTask() {
  if (!currentTask.value) return
  try {
    const response = await fetch(`/v1/tasks/${currentTask.value.id}`)
    currentTask.value = await readJson(response) as TaskView
    if (currentTask.value.result && ['completed', 'waiting_review'].includes(currentTask.value.status)) await loadResult()
    if (currentTask.value.status === 'waiting_review') await loadReviews()
    if (terminal(currentTask.value.status) && pollTimer !== undefined) {
      window.clearInterval(pollTimer)
      pollTimer = undefined
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '读取任务失败'
  }
}

async function loadResult() {
  if (!currentTask.value?.result) return
  try {
    const response = await fetch(`/v1/tasks/${currentTask.value.id}/result`)
    resultContent.value = await readJson(response) as ResultPayload
  } catch (err) {
    error.value = err instanceof Error ? err.message : '无法读取结果内容'
  }
}

async function loadReviews() {
  try {
    const response = await fetch('/v1/reviews?status=pending&size=20')
    const payload = await readJson(response) as { items?: Review[] }
    reviews.value = payload.items || []
  } catch (err) {
    error.value = err instanceof Error ? err.message : '读取复核失败'
  }
}

async function decide(review: Review, decision: 'approve' | 'reject') {
  error.value = ''
  try {
    const response = await fetch(`/v1/reviews/${review.id}/${decision}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resultVersion: review.resultVersion, comment: 'Local demo decision' }),
    })
    await readJson(response)
    await loadReviews()
    await refreshTask()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '复核操作失败'
  }
}

onMounted(() => { void loadReviews() })
onBeforeUnmount(() => { if (pollTimer !== undefined) window.clearInterval(pollTimer) })
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="brand"><span class="brand-mark">LX</span><span><strong>LexCyber</strong><small>通用执行平台 · v0.3</small></span></div>
      <span class="environment">STUB / LOCAL</span>
    </header>

    <main class="content">
      <section class="hero">
        <div>
          <p class="eyebrow">WORKFLOW CONSOLE</p>
          <h1>从任务到结果，<em>每一步都可追踪。</em></h1>
          <p class="lede">这是一个不绑定具体业务规则的开发控制台，用于验证派发、执行、复核、审计和重试链路。</p>
        </div>
        <div class="trace-card"><strong>Java API → Python Engine</strong><small>durable outbox · callback · reconciliation</small></div>
      </section>

      <section class="workspace-grid">
        <article class="panel composer">
          <div class="panel-heading"><h2>提交演示任务</h2><span class="badge">Stub</span></div>
          <label>Query<textarea v-model="query" rows="3" /></label>
          <label>Metadata (JSON)<textarea v-model="metadataText" rows="4" /></label>
          <label class="checkbox"><input v-model="requireReview" type="checkbox" /> 让本次任务进入人工复核</label>
          <button class="primary" :disabled="loading || !query.trim()" type="button" @click="submitTask">{{ loading ? '提交中…' : '提交任务' }}</button>
          <p v-if="error" class="error">{{ error }}</p>
        </article>

        <article class="panel task-panel">
          <div class="panel-heading"><h2>当前任务</h2><span class="status">{{ statusLabel }}</span></div>
          <div v-if="currentTask" class="task-details">
            <p><small>Task ID</small><code>{{ currentTask.id }}</code></p>
            <p><small>Execution</small><code>{{ currentTask.executionId }}</code></p>
            <p><small>Stage</small><strong>{{ currentTask.currentStage }}</strong></p>
            <p v-if="currentTask.result"><small>Result</small><code>{{ currentTask.result.type }} #{{ currentTask.result.version }}</code></p>
            <p v-if="currentTask.error" class="error">{{ currentTask.error }}</p>
            <p v-if="currentTask.errorCode" class="error"><small>Error code</small><code>{{ currentTask.errorCode }}</code></p>
            <pre v-if="resultContent" class="result-json">{{ JSON.stringify(resultContent.content, null, 2) }}</pre>
          </div>
          <p v-else class="empty">提交任务后，这里会显示状态和结果引用。</p>
        </article>
      </section>

      <section class="panel review-panel">
        <div class="panel-heading"><h2>待复核任务</h2><button type="button" @click="loadReviews">刷新</button></div>
        <div v-if="reviews.length === 0" class="empty">暂无待复核任务。</div>
        <div v-for="review in reviews" :key="review.id" class="review-row">
          <span><strong>{{ review.id }}</strong><small>结果版本 {{ review.resultVersion }}</small></span>
          <span class="review-actions"><button type="button" @click="decide(review, 'reject')">拒绝</button><button class="primary" type="button" @click="decide(review, 'approve')">批准</button></span>
        </div>
      </section>
    </main>
  </div>
</template>
