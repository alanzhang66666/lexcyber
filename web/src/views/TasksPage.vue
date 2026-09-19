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
const showAdvanced = ref(false)
const submitting = ref(false)
const loadingRecent = ref(true)
const error = ref('')
const recentTasks = ref<TaskView[]>([])
const queryById = ref<Record<string, string>>({})

type StoredTask = { id: string; query: string }

function storedTasks(): StoredTask[] {
  try {
    const value = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]') as unknown
    if (!Array.isArray(value)) return []
    return value.flatMap((item) => {
      if (typeof item === 'string') return [{ id: item, query: '' }]
      if (item && typeof item === 'object' && 'id' in item && typeof (item as StoredTask).id === 'string') {
        return [{ id: (item as StoredTask).id, query: String((item as StoredTask).query || '') }]
      }
      return []
    }).slice(0, 10)
  } catch {
    return []
  }
}

function rememberTask(task: TaskView, submittedQuery: string) {
  const next = [{ id: task.id, query: submittedQuery }, ...storedTasks().filter((item) => item.id !== task.id)].slice(0, 10)
  localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
}

function titleFor(task: TaskView) {
  const local = queryById.value[task.id]?.trim()
  if (local) return local
  return task.caseId || task.id
}

async function loadRecent() {
  loadingRecent.value = true
  const stored = storedTasks()
  queryById.value = Object.fromEntries(stored.map((item) => [item.id, item.query]))
  const results = await Promise.allSettled(stored.map((item) => api.getTask(item.id)))
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
    if (!metadata || Array.isArray(metadata) || typeof metadata !== 'object') throw new Error('高级选项必须是 JSON 对象。')
    const normalizedMetadata = { ...(metadata as Record<string, unknown>) }
    if (requireReview.value) normalizedMetadata.demo_requires_review = true
    const task = await api.createTask({
      query: query.value.trim(),
      ...(caseId.value.trim() ? { caseId: caseId.value.trim() } : {}),
      metadata: normalizedMetadata,
    })
    rememberTask(task, query.value.trim())
    await router.push({ name: 'task-detail', params: { taskId: task.id } })
  } catch (caught) {
    error.value = caught instanceof SyntaxError
      ? '高级选项不是有效的 JSON。'
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
        <p class="eyebrow">执行任务</p>
        <h1>执行任务</h1>
        <p>向引擎提交一次分析请求，持续追踪执行阶段、结果版本与审计标识。这是当前已接通的联调入口。</p>
      </div>
      <div class="heading-aside">
        <span class="aside-label">执行原则</span>
        <strong>可追踪 · 可复核 · 不替代裁量</strong>
      </div>
    </header>
    <section class="work-grid">
      <article class="panel composer-panel">
        <div class="panel-heading">
          <div><p class="section-index">01</p><h2>提交分析请求</h2></div>
        </div>
        <form class="form-stack" @submit.prevent="submitTask">
          <label>
            <span>待分析问题 / 材料摘要 <b aria-hidden="true">*</b></span>
            <textarea v-model="query" rows="7" maxlength="20000" required placeholder="输入需要核验的案情摘要、争议点或电子证据说明" />
            <small>{{ query.length.toLocaleString() }} / 20,000</small>
          </label>
          <label>
            <span>案件标识 <i>可选</i></span>
            <input v-model="caseId" autocomplete="off" placeholder="若已有业务案号或案件标识，可在此关联" />
          </label>
          <label class="check-row">
            <input v-model="requireReview" type="checkbox" />
            <span><strong>进入人工复核</strong><small>勾选后将请求复核链路，完成后可在「人工复核」中决定。</small></span>
          </label>
          <button class="text-button" type="button" @click="showAdvanced = !showAdvanced">
            {{ showAdvanced ? '收起高级选项' : '高级选项（JSON）' }}
          </button>
          <label v-if="showAdvanced">
            <span>Metadata</span>
            <textarea v-model="metadataText" class="mono-field" rows="5" spellcheck="false" />
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
        <p class="panel-note">列表仅保存本浏览器提交过的请求，状态始终从服务端读取。</p>
        <div v-if="loadingRecent" class="empty-state" aria-live="polite">正在读取最近任务…</div>
        <div v-else-if="!recentTasks.length" class="empty-state">
          <span aria-hidden="true">＋</span>
          <strong>还没有本地任务记录</strong>
          <p>提交第一条分析请求后，可在此追踪执行阶段和结果版本。</p>
        </div>
        <ul v-else class="record-list">
          <li v-for="task in recentTasks" :key="task.id">
            <RouterLink :to="{ name: 'task-detail', params: { taskId: task.id } }">
              <div class="record-main">
                <span class="truncate">{{ titleFor(task) }}</span>
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
