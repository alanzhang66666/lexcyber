<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import type { CaseView, DocumentRole, DocumentView, ParseStatus, ResultPayload, TaskStatus } from '../api-types'
import CaseFactsPanel from '../components/CaseFactsPanel.vue'
import DocumentParseResult from '../components/DocumentParseResult.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { rememberT1Case } from '../lib/current-case'

const route = useRoute()
const caseId = computed(() => String(route.params.caseId))

const loading = ref(true)
const error = ref('')
const caseItem = ref<CaseView | null>(null)

const docsLoading = ref(false)
const docsError = ref('')
const documents = ref<DocumentView[]>([])

const uploading = ref(false)
const uploadError = ref('')
const file = ref<File | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const role = ref<DocumentRole>('input')

const selectedDocId = ref<string | null>(null)
const resultLoading = ref(false)
const resultError = ref('')
const result = ref<ResultPayload | null>(null)
const failure = ref<{ errorCode?: string | null; error?: string | null } | null>(null)

const TERMINAL: TaskStatus[] = ['completed', 'waiting_review', 'failed', 'timed_out', 'rejected']
let pollTimer: number | undefined

function isTaskStatus(status: ParseStatus): status is TaskStatus {
  return status !== 'not_started'
}

function isTerminal(status: ParseStatus): boolean {
  return status !== 'not_started' && (TERMINAL as string[]).includes(status)
}

function selectedDocument() {
  return documents.value.find((d) => d.id === selectedDocId.value) ?? null
}

async function loadCase() {
  loading.value = true
  error.value = ''
  try {
    caseItem.value = await api.getCase(caseId.value)
    rememberT1Case(caseItem.value.id)
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '案件读取失败。'
  } finally {
    loading.value = false
  }
}

async function refreshStatuses() {
  const pending = documents.value.filter((d) => d.parseTaskId && !isTerminal(d.parseStatus))
  if (!pending.length) {
    stopPolling()
    return
  }
  await Promise.all(pending.map(async (doc) => {
    if (!doc.parseTaskId) return
    try {
      const task = await api.getTask(doc.parseTaskId)
      doc.parseStatus = task.status as ParseStatus
    } catch {
      /* 保留现有状态，等待下一轮 */
    }
  }))
}

function startPolling() {
  stopPolling()
  pollTimer = window.setInterval(() => void refreshStatuses(), 2000)
}

function stopPolling() {
  if (pollTimer !== undefined) {
    window.clearInterval(pollTimer)
    pollTimer = undefined
  }
}

async function loadDocuments() {
  docsLoading.value = true
  docsError.value = ''
  try {
    const page = await api.listDocuments(caseId.value, { page: 0, size: 50 })
    documents.value = page.items
    await refreshStatuses()
    if (documents.value.some((d) => d.parseTaskId && !isTerminal(d.parseStatus))) startPolling()
  } catch (caught) {
    docsError.value = caught instanceof Error ? caught.message : '材料列表读取失败。'
  } finally {
    docsLoading.value = false
  }
}

function onFileChange(event: Event) {
  const target = event.target as HTMLInputElement
  file.value = target.files?.[0] ?? null
}

async function upload() {
  if (!file.value) return
  uploading.value = true
  uploadError.value = ''
  try {
    await api.uploadDocument(caseId.value, file.value, role.value)
    file.value = null
    if (fileInput.value) fileInput.value.value = ''
    await loadDocuments()
  } catch (caught) {
    uploadError.value = caught instanceof Error ? caught.message : '上传失败。'
  } finally {
    uploading.value = false
  }
}

async function openDoc(doc: DocumentView) {
  if (!doc.parseTaskId) return
  selectedDocId.value = doc.id
  resultLoading.value = true
  resultError.value = ''
  result.value = null
  failure.value = null
  try {
    if (doc.parseStatus === 'completed') {
      result.value = await api.getTaskResult(doc.parseTaskId)
    } else {
      const task = await api.getTask(doc.parseTaskId)
      failure.value = { errorCode: task.errorCode, error: task.error }
    }
  } catch (caught) {
    resultError.value = caught instanceof Error ? caught.message : '解析详情读取失败。'
  } finally {
    resultLoading.value = false
  }
}

onMounted(() => {
  void loadCase()
  void loadDocuments()
})

onUnmounted(stopPolling)
</script>

<template>
  <div class="page-stack">
    <header class="page-heading">
      <div>
        <RouterLink class="back-link" to="/cases">← 返回案件中心</RouterLink>
        <p class="eyebrow">案件工作区</p>
        <h1>{{ caseItem?.title || '案件' }}</h1>
        <p v-if="caseItem">{{ caseItem.jurisdiction || '未填法域' }}{{ caseItem.asOfDate ? ' · ' + caseItem.asOfDate : '' }}</p>
      </div>
      <RouterLink
        v-if="caseItem"
        class="button button-quiet"
        :to="`/cases/${caseItem.id}/docket`"
      >打开阅卷</RouterLink>
    </header>

    <div v-if="loading" class="panel empty-state" aria-live="polite">正在读取案件…</div>

    <div v-else-if="error" class="panel">
      <p class="notice notice-error" role="alert">{{ error }}</p>
      <button class="button button-quiet" type="button" @click="loadCase">重试</button>
    </div>

    <template v-else>
      <section class="detail-grid">
        <article class="panel">
          <div class="panel-heading"><div><p class="section-index">01</p><h2>材料上传</h2></div></div>
          <form class="form-stack" @submit.prevent="upload">
            <label>
              <span>材料类型 <b>*</b></span>
              <select v-model="role">
                <option value="input">输入材料</option>
                <option value="annotation">法学标注</option>
              </select>
            </label>
            <label>
              <span>选择文件 <b>*</b></span>
              <input ref="fileInput" type="file" @change="onFileChange" />
            </label>
            <p v-if="uploadError" class="notice notice-error" role="alert">{{ uploadError }}</p>
            <button class="button button-primary" type="submit" :disabled="uploading || !file">
              {{ uploading ? '上传中…' : '上传材料' }}
            </button>
          </form>
        </article>

        <article class="panel">
          <div class="panel-heading">
            <div><p class="section-index">02</p><h2>材料列表</h2></div>
            <button class="button button-quiet" type="button" :disabled="docsLoading" @click="loadDocuments">刷新</button>
          </div>
          <p class="panel-note">上传成功后自动发起解析任务，状态每 2 秒刷新；完成后可查看正文与原文定位。</p>
          <div v-if="docsLoading" class="empty-state" aria-live="polite">正在读取材料…</div>
          <p v-else-if="docsError" class="notice notice-error" role="alert">{{ docsError }}</p>
          <div v-else-if="!documents.length" class="empty-state">
            <strong>还没有材料</strong>
            <p>上传第一份材料后，将自动发起解析任务。</p>
          </div>
          <ul v-else class="record-list">
            <li v-for="doc in documents" :key="doc.id">
              <div class="doc-row">
                <div class="record-main">
                  <span>{{ doc.filename }}</span>
                  <small>{{ doc.role === 'annotation' ? '法学标注' : '输入材料' }}</small>
                </div>
                <div class="doc-actions">
                  <StatusBadge v-if="isTaskStatus(doc.parseStatus)" :status="doc.parseStatus" />
                  <span v-else class="subtle-chip">未开始</span>
                  <button
                    v-if="doc.parseTaskId && (doc.parseStatus === 'completed' || doc.parseStatus === 'failed' || doc.parseStatus === 'timed_out')"
                    class="button button-quiet"
                    type="button"
                    @click="openDoc(doc)"
                  >
                    {{ doc.parseStatus === 'completed' ? '查看正文' : '查看错误' }}
                  </button>
                </div>
              </div>
            </li>
          </ul>
        </article>
      </section>

      <CaseFactsPanel :case-id="caseId" />

      <section v-if="selectedDocId" class="panel result-panel">
        <div class="panel-heading">
          <div>
            <p class="section-index">04</p>
            <h2>解析详情</h2>
          </div>
          <button class="button button-quiet" type="button" @click="selectedDocId = null">关闭</button>
        </div>
        <p class="panel-note">{{ selectedDocument()?.filename || '' }}</p>
        <div v-if="resultLoading" class="empty-state" aria-live="polite">正在读取解析详情…</div>
        <p v-else-if="resultError" class="notice notice-error" role="alert">{{ resultError }}</p>
        <div v-else-if="failure" class="notice notice-error" role="alert">
          <strong>{{ failure.errorCode || 'PARSE_FAILED' }}</strong>
          <span>{{ failure.error || '解析未返回更多错误信息。' }}</span>
        </div>
        <div v-else-if="result" class="result-block">
          <DocumentParseResult :content="result.content" />
        </div>
        <div v-else class="empty-state">该材料尚未产生可显示的解析结果。</div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.doc-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 14px 8px;
}
.doc-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 0 0 auto;
}
</style>
