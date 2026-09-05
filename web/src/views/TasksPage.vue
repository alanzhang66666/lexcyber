<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import type { TaskView } from '../api-types'
import StatusBadge from '../components/StatusBadge.vue'

const STORAGE_KEY = 'lexcyber.recent-task-ids'
const router = useRouter()
const query = ref('')
const caseId = ref('')
const metadataText = ref('{}')
const requireReview = ref(false)
const submitting = ref(false)
const loadingRecent = ref(true)
const error = ref('')
const recentTasks = ref<TaskView[]>([])

function storedIds() {
  try {
    const value = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')
    return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string').slice(0, 10) : []
  } catch {
    return []
  }
}

function rememberTask(task: TaskView) {
  const ids = [task.id, ...storedIds().filter((id) => id !== task.id)].slice(0, 10)
  localStorage.setItem(STORAGE_KEY, JSON.stringify(ids))
}

async function loadRecent() {
  loadingRecent.value = true
  const results = await Promise.allSettled(storedIds().map((id) => api.getTask(id)))
  recentTasks.value = results
    .filter((item): item is PromiseFulfilledResult<TaskView> => item.status === 'fulfilled')
    .map((item) => item.value)
  loadingRecent.value = false
}

async function submitTask() {
  error.value = ''
  submitting.value = true
  try {
    const metadata = JSON.parse(metadataText.value || '{}') as unknown
    if (!metadata || Array.isArray(metadata) || typeof metadata !== 'object') throw new Error('Metadata 必须是 JSON 对象。')
    const normalizedMetadata = { ...(metadata as Record<string, unknown>) }
    if (requireReview.value) normalizedMetadata.demo_requires_review = true
    const task = await api.createTask({
      query: query.value.trim(),
      ...(caseId.value.trim() ? { caseId: caseId.value.trim() } : {}),
      metadata: normalizedMetadata,
    })
    rememberTask(task)
    await router.push({ name: 'task-detail', params: { taskId: task.id } })
  } catch (caught) {
    error.value = caught instanceof SyntaxError
      ? 'Metadata 不是有效的 JSON。'
      : caught instanceof Error ? caught.message : '任务提交失败。'
  } finally {
    submitting.value = false
  }
}

function formatTime(value?: string | null) {
  return value ? new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : '—'
}

onMounted(() => void loadRecent())
</script>

<template>
  <div class="page-stack">
    <header class="page-heading">
      <div>
        <p class="eyebrow">TASK INTAKE</p>
        <h1>任务中心</h1>
        <p>提交执行请求，持续追踪每次执行的阶段、结果与审计标识。</p>
      </div>
      <div class="heading-aside">
        <span class="aside-label">执行原则</span>
        <strong>可追踪 · 可复核 · 不替代裁量</strong>
      </div>
    </header>
    <section class="work-grid">
      <article class="panel composer-panel">
        <div class="panel-heading">
          <div><p class="section-index">01</p><h2>提交新任务</h2></div>
          <span class="subtle-chip">POST /v1/tasks</span>
        </div>
        <form class="form-stack" @submit.prevent="submitTask">
          <label>
            <span>任务内容 <b aria-hidden="true">*</b></span>
            <textarea v-model="query" rows="7" maxlength="20000" required placeholder="输入需要执行引擎处理的任务内容" />
            <small>{{ query.length.toLocaleString() }} / 20,000</small>
          </label>
          <label>
            <span>案件标识 <i>可选</i></span>
            <input v-model="caseId" autocomplete="off" placeholder="仅在已有业务标识时填写" />
          </label>
          <label>
            <span>Metadata <i>JSON 对象</i></span>
            <textarea v-model="metadataText" class="mono-field" rows="5" spellcheck="false" />
          </label>
          <label class="check-row">
            <input v-model="requireReview" type="checkbox" />
            <span><strong>进入人工复核</strong><small>演示环境将通过 metadata 请求复核链路。</small></span>
          </label>
          <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
          <button class="button button-primary" :disabled="submitting || !query.trim()" type="submit">
            {{ submitting ? '正在提交…' : '提交任务' }}
          </button>
        </form>
      </article>
      <article class="panel recent-panel">
        <div class="panel-heading">
          <div><p class="section-index">02</p><h2>最近任务</h2></div>
          <button class="button button-quiet" :disabled="loadingRecent" type="button" @click="loadRecent">刷新</button>
        </div>
        <p class="panel-note">列表仅保存本浏览器提交过的任务标识，状态始终从服务端读取。</p>
        <div v-if="loadingRecent" class="empty-state" aria-live="polite">正在读取最近任务…</div>
        <div v-else-if="!recentTasks.length" class="empty-state">
          <span aria-hidden="true">＋</span><strong>还没有本地任务记录</strong><p>提交第一条任务后，它会出现在这里。</p>
        </div>
        <ul v-else class="record-list">
          <li v-for="task in recentTasks" :key="task.id">
            <RouterLink :to="{ name: 'task-detail', params: { taskId: task.id } }">
              <div class="record-main">
                <span class="mono truncate">{{ task.id }}</span>
                <small>{{ task.currentStage || '等待阶段信息' }} · {{ formatTime(task.updatedAt || task.createdAt) }}</small>
              </div>
              <StatusBadge :status="task.status" />
            </RouterLink>
          </li>
        </ul>
      </article>
    </section>
  </div>
</template>
