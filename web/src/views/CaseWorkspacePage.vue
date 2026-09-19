<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import type { CaseView, DocumentRole, DocumentView, ParseStatus, ResultPayload, TaskStatus } from '../api-types'
import CaseFactsPanel from '../components/CaseFactsPanel.vue'
import CaseRelationsPanel from '../components/CaseRelationsPanel.vue'
import DocumentParseResult from '../components/DocumentParseResult.vue'
import ExtractCandidatesPanel from '../components/ExtractCandidatesPanel.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { rememberT1Case } from '../lib/current-case'
import { extractCandidatesFromParse, type ExtractGroup } from '../lib/extract-candidates'

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
const targetLocator = ref<string | null>(null)
const locateNotice = ref('')
const extractGroups = ref<ExtractGroup[]>([])

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
    await loadExtracts()
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
  if (!documents.value.some((d) => d.parseTaskId && !isTerminal(d.parseStatus))) {
    stopPolling()
    await loadExtracts()
  }
}

async function loadExtracts() {
  const completed = documents.value.filter((doc) => (
    doc.role !== 'annotation' && doc.parseStatus === 'completed' && doc.parseTaskId
  ))
  if (!completed.length) {
    extractGroups.value = []
    return
  }
  const groups = await Promise.all(completed.map(async (doc) => {
    try {
      const payload = await api.getTaskResult(doc.parseTaskId as string)
      const candidates = extractCandidatesFromParse(payload.content)
      return candidates.length
        ? { documentId: doc.id, filename: doc.filename, candidates }
        : null
    } catch {
      return null
    }
  }))
  extractGroups.value = groups.filter((group): group is ExtractGroup => group !== null)
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

/** 从材料列表点「查看正文/错误」，不携带定位目标。 */
function openDocFromList(doc: DocumentView) {
  targetLocator.value = null
  locateNotice.value = ''
  void openDoc(doc)
}

/** 点击事实/关系里的原文定位：打开对应材料并滚动到该段落。 */
function handleLocate(documentId: string | undefined, locator: string) {
  targetLocator.value = locator
  locateNotice.value = ''
  const doc = documentId ? documents.value.find((d) => d.id === documentId) : undefined
  if (doc && doc.parseTaskId) {
    void openDoc(doc)
    return
  }
  locateNotice.value = documentId
    ? '该定位对应的材料尚未上传或解析完成，无法回跳原文。'
    : '该条目未关联材料，无法回跳原文。'
}

function closeResult() {
  selectedDocId.value = null
  targetLocator.value = null
  locateNotice.value = ''
}

onMounted(() => {
  void loadCase()
  void loadDocuments()
})

onUnmounted(stopPolling)
</script>

<template>
  <div class="page-stack">
    <header class="page-heading workspace-heading">
      <div>
        <RouterLink class="back-link" to="/cases">← 返回案件中心</RouterLink>
        <p class="eyebrow">案件工作区</p>
        <h1>{{ caseItem?.title || '案件' }}</h1>
        <p v-if="caseItem">{{ caseItem.jurisdiction || '未填法域' }}{{ caseItem.asOfDate ? ' · ' + caseItem.asOfDate : '' }}</p>
      </div>
      <nav v-if="caseItem" class="module-nav" aria-label="案件模块">
        <RouterLink class="button button-quiet" :to="`/cases/${caseItem.id}/compliance`">合规筛查</RouterLink>
        <RouterLink class="button button-quiet" :to="`/cases/${caseItem.id}/conviction`">定罪研判</RouterLink>
        <RouterLink class="button button-quiet" :to="`/cases/${caseItem.id}/analysis`">量刑分析</RouterLink>
        <RouterLink class="button button-quiet" :to="`/cases/${caseItem.id}/docket`">打开阅卷</RouterLink>
        <RouterLink class="button button-quiet" :to="`/cases/${caseItem.id}/documents`">文书辅助</RouterLink>
      </nav>
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
            <div class="field">
              <span class="field-label">选择文件 <b>*</b></span>
              <div class="file-picker">
                <div class="file-drop" :class="{ 'is-filled': file }">
                  <span v-if="file" class="file-name" :title="file.name">{{ file.name }}</span>
                  <span v-else class="file-placeholder">未选择文件</span>
                </div>
                <button class="button button-quiet" type="button" @click="fileInput?.click()">选择文件</button>
                <input ref="fileInput" type="file" class="file-input-hidden" @change="onFileChange" />
              </div>
            </div>
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
          <p class="panel-note">上传成功后自动发起解析任务，状态每 2 秒刷新；解析完成后再对照抽取候选与已核对标注，并可回跳原文。</p>
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
                    @click="openDocFromList(doc)"
                  >
                    {{ doc.parseStatus === 'completed' ? '查看正文' : '查看错误' }}
                  </button>
                </div>
              </div>
            </li>
          </ul>
        </article>
      </section>

      <ExtractCandidatesPanel :groups="extractGroups" @locate="handleLocate" />

      <CaseRelationsPanel :case="caseItem" @locate="handleLocate" />

      <CaseFactsPanel :case-id="caseId" @locate="handleLocate" />

      <section v-if="selectedDocId" class="panel result-panel">
        <div class="panel-heading">
          <div>
            <p class="section-index">05</p>
            <h2>解析详情</h2>
          </div>
          <button class="button button-quiet" type="button" @click="closeResult">关闭</button>
        </div>
        <p class="panel-note">{{ selectedDocument()?.filename || '' }}</p>
        <p v-if="locateNotice" class="notice notice-warning" role="status">{{ locateNotice }}</p>
        <div v-if="resultLoading" class="empty-state" aria-live="polite">正在读取解析详情…</div>
        <p v-else-if="resultError" class="notice notice-error" role="alert">{{ resultError }}</p>
        <div v-else-if="failure" class="notice notice-error" role="alert">
          <strong>{{ failure.errorCode || 'PARSE_FAILED' }}</strong>
          <span>{{ failure.error || '解析未返回更多错误信息。' }}</span>
        </div>
        <div v-else-if="result" class="result-block">
          <DocumentParseResult :content="result.content" :target-locator="targetLocator" />
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
.field {
  display: grid;
  gap: 7px;
  color: var(--lc-ink);
  font-size: 13px;
  font-weight: 700;
}
.field-label b { color: var(--lc-risk); }
.file-picker { display: flex; align-items: stretch; gap: 10px; }
.file-drop {
  flex: 1;
  min-width: 0;
  min-height: 42px;
  display: grid;
  place-items: center;
  padding: 0 14px;
  color: var(--lc-muted);
  background: var(--lc-surface-alt);
  border: 1px dashed #c9c3d6;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  text-align: center;
  transition: border-color .15s, background .15s, color .15s;
}
.file-drop.is-filled {
  color: var(--lc-brand-900);
  background: var(--lc-brand-100);
  border-style: solid;
  border-color: var(--lc-brand-500);
}
.file-name {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.file-input-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  clip-path: inset(50%);
  white-space: nowrap;
  border: 0;
}
</style>
