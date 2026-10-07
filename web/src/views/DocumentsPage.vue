<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, apiV2 } from '../api'
import type { CaseView, DraftView } from '../api-types'
import { isPlaceholderCaseId } from '../data/placeholder-cases'
import { rememberT1Case } from '../lib/current-case'
import { toV2Draft } from '../lib/module-content-v2'

const route = useRoute()
const caseId = computed(() => String(route.params.caseId || ''))

const loading = ref(true)
const error = ref('')
const caseItem = ref<CaseView | null>(null)
const drafts = ref<DraftView[]>([])

const selectedId = ref<string | null>(null)
const editing = ref(false)
const draftBody = ref('')
const saving = ref(false)
const saveError = ref('')

const newType = ref('')
const creating = ref(false)
const createError = ref('')

const submitting = ref(false)
const submitError = ref('')
const submitOk = ref('')

const renderDocType = ref('')
const rendering = ref(false)
const renderError = ref('')
const renderedBody = ref('')
const renderedMeta = ref<Record<string, unknown> | null>(null)
const downloadError = ref('')
const downloading = ref(false)

let loadGeneration = 0

const RENDER_POLL_MS = 1500
const RENDER_POLL_LIMIT = 80

const workspaceTo = computed(() => (caseItem.value ? `/cases/${caseItem.value.id}` : '/cases'))
const selectedDraft = computed(() => drafts.value.find((d) => d.id === selectedId.value) ?? null)
const bodyEmpty = computed(() => !(selectedDraft.value?.body ?? '').trim())
const hasPlaceholder = computed(() => /【[^】]*】|\{\{[^{}]*\}\}/.test(selectedDraft.value?.body ?? ''))
const canSubmit = computed(() => Boolean(selectedDraft.value) && !bodyEmpty.value && !hasPlaceholder.value)
const manualArtifactId = computed(() => selectedDraft.value?.artifactVersionId ?? null)
const canDownloadManual = computed(() => Boolean(manualArtifactId.value) && canSubmit.value)
const renderedArtifactId = computed(() => typeof renderedMeta.value?.artifactVersionId === 'string'
  ? renderedMeta.value.artifactVersionId : null)
const renderedBlockers = computed(() => Array.isArray(renderedMeta.value?.blockers)
  ? renderedMeta.value.blockers : [])
const renderedHasPlaceholder = computed(() => /【[^】]*】|\{\{[^{}]*\}\}/.test(renderedBody.value))
const canDownloadRendered = computed(() => Boolean(renderedArtifactId.value)
  && Boolean(renderedBody.value.trim())
  && String(renderedMeta.value?.outcomeStatus ?? '') === 'calculated'
  && !renderedHasPlaceholder.value
  && renderedBlockers.value.length === 0)

function formatTime(value?: string | null) {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(d)
}

function isCurrent(generation: number, expectedCaseId: string) {
  return generation === loadGeneration && expectedCaseId === caseId.value
}

function clearCaseState() {
  caseItem.value = null
  drafts.value = []
  selectedId.value = null
  draftBody.value = ''
  editing.value = false
  renderedBody.value = ''
  renderedMeta.value = null
  downloadError.value = ''
  saving.value = false
  saveError.value = ''
  creating.value = false
  createError.value = ''
  submitting.value = false
  submitError.value = ''
  submitOk.value = ''
  rendering.value = false
  renderError.value = ''
  downloading.value = false
}

async function loadCase() {
  const generation = ++loadGeneration
  const expectedCaseId = caseId.value
  loading.value = true
  error.value = ''
  clearCaseState()
  if (!expectedCaseId || isPlaceholderCaseId(expectedCaseId)) {
    loading.value = false
    return
  }
  try {
    const loadedCase = await api.getCase(expectedCaseId)
    if (!isCurrent(generation, expectedCaseId)) return
    caseItem.value = loadedCase
    rememberT1Case(caseItem.value.id)
    await loadDrafts(expectedCaseId, generation)
    if (!isCurrent(generation, expectedCaseId)) return
    try {
      await loadRendered(undefined, expectedCaseId, generation)
    } catch {
      // 尚无渲染流时保持空态，不阻塞手工草稿区
    }
  } catch (caught) {
    if (isCurrent(generation, expectedCaseId)) {
      error.value = caught instanceof Error ? caught.message : '案件读取失败。'
    }
  } finally {
    if (isCurrent(generation, expectedCaseId)) loading.value = false
  }
}

async function loadDrafts(expectedCaseId = caseId.value, generation = loadGeneration) {
  const list = await api.listCaseDrafts(expectedCaseId)
  if (!isCurrent(generation, expectedCaseId)) return
  drafts.value = list.items
  if (!drafts.value.some((d) => d.id === selectedId.value)) {
    selectedId.value = drafts.value[0]?.id ?? null
  }
}

function selectDraft(draft: DraftView) {
  selectedId.value = draft.id
  editing.value = false
  draftBody.value = ''
  saveError.value = ''
}

function startEdit() {
  if (!selectedDraft.value) return
  draftBody.value = selectedDraft.value.body
  editing.value = true
  saveError.value = ''
}

function cancelEdit() {
  editing.value = false
  draftBody.value = ''
}

async function save() {
  if (!selectedDraft.value) return
  const expectedCaseId = caseId.value
  const generation = loadGeneration
  const draftId = selectedDraft.value.id
  const version = selectedDraft.value.version
  const body = draftBody.value
  saving.value = true
  saveError.value = ''
  try {
    const updated = await api.putCaseDraft(expectedCaseId, draftId, {
      body,
      version,
    })
    if (!isCurrent(generation, expectedCaseId)) return
    const index = drafts.value.findIndex((d) => d.id === updated.id)
    if (index >= 0) drafts.value[index] = updated
    else drafts.value.push(updated)
    selectedId.value = updated.id
    editing.value = false
  } catch (caught) {
    if (isCurrent(generation, expectedCaseId)) {
      saveError.value = caught instanceof Error ? caught.message : '保存失败。'
    }
  } finally {
    if (isCurrent(generation, expectedCaseId)) saving.value = false
  }
}

async function create() {
  const type = newType.value.trim()
  if (!type) return
  creating.value = true
  createError.value = ''
  const expectedCaseId = caseId.value
  const generation = loadGeneration
  try {
    const draft = await api.createCaseDraft(expectedCaseId, { draftType: type, body: '' })
    if (!isCurrent(generation, expectedCaseId)) return
    drafts.value = [draft, ...drafts.value]
    selectedId.value = draft.id
    newType.value = ''
    editing.value = false
  } catch (caught) {
    if (isCurrent(generation, expectedCaseId)) {
      createError.value = caught instanceof Error ? caught.message : '新建失败。'
    }
  } finally {
    if (isCurrent(generation, expectedCaseId)) creating.value = false
  }
}

async function submitReview() {
  if (!selectedDraft.value || !canSubmit.value) return
  const expectedCaseId = caseId.value
  const generation = loadGeneration
  const draftId = selectedDraft.value.id
  const draftVersion = selectedDraft.value.version
  submitting.value = true
  submitError.value = ''
  submitOk.value = ''
  try {
    await api.openCaseReview(expectedCaseId, {
      module: 'sentencing',
      draftId,
      draftVersion,
    })
    if (!isCurrent(generation, expectedCaseId)) return
    submitOk.value = '已提交人工复核。'
  } catch (caught) {
    if (isCurrent(generation, expectedCaseId)) {
      submitError.value = caught instanceof Error ? caught.message : '提交复核失败。'
    }
  } finally {
    if (isCurrent(generation, expectedCaseId)) submitting.value = false
  }
}

async function pollExecutionDone(executionId: string, expectedCaseId: string, generation: number) {
  for (let attempt = 0; attempt < RENDER_POLL_LIMIT; attempt += 1) {
    if (!isCurrent(generation, expectedCaseId)) return false
    const exec = await apiV2.getExecution(executionId)
    if (!isCurrent(generation, expectedCaseId)) return false
    const state = String(exec.state ?? '')
    if (state === 'completed') return true
    if (state === 'failed') throw new Error('文书渲染执行失败。')
    await new Promise((resolve) => window.setTimeout(resolve, RENDER_POLL_MS))
  }
  throw new Error('文书渲染超时，请稍后在任务中心查看。')
}

async function loadRendered(docType?: string, expectedCaseId = caseId.value, generation = loadGeneration) {
  const list = await apiV2.listDraftStreams(expectedCaseId)
  if (!isCurrent(generation, expectedCaseId)) return
  const items = list.items ?? []
  const target = docType
    ? items.find((i) => i.docType === docType)
    : items[items.length - 1]
  const latestId = target?.latestVersionId as string | null | undefined
  if (!latestId) {
    if (!isCurrent(generation, expectedCaseId)) return
    renderedBody.value = ''
    renderedMeta.value = null
    return
  }
  const artifact = await apiV2.getArtifactVersion(latestId)
  if (!isCurrent(generation, expectedCaseId)) return
  const payload = (artifact.payload ?? {}) as Record<string, unknown>
  const draft = toV2Draft(payload)
  renderedBody.value = draft?.body ?? ''
  renderedMeta.value = {
    artifactVersionId: artifact.artifactVersionId ?? latestId,
    docType: draft?.docType ?? target?.docType,
    version: artifact.version,
    outcomeStatus: artifact.outcomeStatus,
    blockers: draft?.unresolved?.length ? draft.unresolved : artifact.blockers,
    dependencySnapshot: artifact.dependencySnapshot,
  }
}

async function renderDraft() {
  const docType = renderDocType.value.trim()
  if (!docType) return
  const expectedCaseId = caseId.value
  const generation = loadGeneration
  rendering.value = true
  renderError.value = ''
  try {
    const created = await apiV2.dispatchDraftRender(expectedCaseId, docType)
    const executionId = String(created.executionId ?? '')
    if (!executionId) throw new Error('派发响应缺少 executionId')
    const completed = await pollExecutionDone(executionId, expectedCaseId, generation)
    if (!completed || !isCurrent(generation, expectedCaseId)) return
    await loadRendered(docType, expectedCaseId, generation)
  } catch (caught) {
    if (isCurrent(generation, expectedCaseId)) {
      renderError.value = caught instanceof Error ? caught.message : '文书渲染失败。'
    }
  } finally {
    if (isCurrent(generation, expectedCaseId)) rendering.value = false
  }
}

async function downloadArtifact(expectedCaseId: string, artifactVersionId: string, generation: number) {
  if (!isCurrent(generation, expectedCaseId)) return
  downloading.value = true
  downloadError.value = ''
  try {
    const result = await apiV2.exportArtifactDocx(expectedCaseId, artifactVersionId)
    if (!isCurrent(generation, expectedCaseId)) return
    const objectUrl = URL.createObjectURL(result.blob)
    const anchor = document.createElement('a')
    anchor.href = objectUrl
    anchor.download = result.filename
    try {
      anchor.click()
    } finally {
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0)
    }
  } catch (caught) {
    if (isCurrent(generation, expectedCaseId)) {
      downloadError.value = caught instanceof Error ? caught.message : '文书下载失败。'
    }
  } finally {
    if (isCurrent(generation, expectedCaseId)) downloading.value = false
  }
}

function downloadManual() {
  const id = manualArtifactId.value
  if (id && canDownloadManual.value) void downloadArtifact(caseId.value, id, loadGeneration)
}

function downloadRendered() {
  const id = renderedArtifactId.value
  if (id && canDownloadRendered.value) void downloadArtifact(caseId.value, id, loadGeneration)
}

onMounted(() => void loadCase())
watch(caseId, (next, previous) => {
  if (next !== previous) void loadCase()
})
onBeforeUnmount(() => { loadGeneration += 1 })
</script>

<template>
  <div class="page-stack">
    <header class="page-heading">
      <div>
        <RouterLink class="back-link" :to="workspaceTo">← 返回案件工作区</RouterLink>
        <p class="eyebrow">文书辅助</p>
        <h1>文书辅助</h1>
        <p>{{ caseItem?.title || '当前案件' }} · 按已核对标注整理文书草稿，字段映射仍待法学会签</p>
      </div>
    </header>

    <div v-if="loading" class="panel empty-state" aria-live="polite">正在读取案件与文书草稿…</div>

    <div v-else-if="error" class="panel">
      <p class="notice notice-error" role="alert">{{ error }}</p>
      <button class="button button-quiet" type="button" @click="loadCase">重试</button>
    </div>

    <div v-else-if="isPlaceholderCaseId(caseId)" class="panel empty-state">
      <strong>请先选择真实案件</strong>
      <p>文书草稿挂在具体案件下。请到案件中心新建或选择案件。</p>
      <RouterLink class="button button-primary" to="/cases">前往案件中心</RouterLink>
    </div>

    <div v-else class="documents-layout">
      <section class="panel">
        <div class="panel-heading">
          <div><p class="section-index">01</p><h2>文书列表</h2></div>
          <button class="button button-quiet" type="button" :disabled="loading" @click="loadDrafts()">刷新</button>
        </div>

        <form class="form-stack create-row" @submit.prevent="create">
          <label>
            <span>新建文书类型</span>
            <input v-model="newType" placeholder="文书类型，如审查报告" />
          </label>
          <p v-if="createError" class="notice notice-error" role="alert">{{ createError }}</p>
          <button class="button button-primary" type="submit" :disabled="creating || !newType.trim()">
            {{ creating ? '新建中…' : '新建文书' }}
          </button>
        </form>

        <ul v-if="drafts.length" class="record-list">
          <li v-for="draft in drafts" :key="draft.id">
            <button class="draft-row" :class="{ 'is-active': draft.id === selectedId }" type="button" @click="selectDraft(draft)">
              <div class="record-main">
                <span>{{ draft.draftType }}</span>
                <small>v{{ draft.version }} · {{ formatTime(draft.updatedAt) }}<template v-if="draft.updatedBy"> · {{ draft.updatedBy }}</template></small>
              </div>
              <span v-if="/【待补充】/.test(draft.body)" class="subtle-chip chip-pending">含待补充</span>
            </button>
          </li>
        </ul>
        <div v-else class="empty-state">
          <strong>还没有文书草稿</strong>
          <p>填写文书类型后点击「新建文书」开始。</p>
        </div>
      </section>

      <section class="panel">
        <div class="panel-heading">
          <div><p class="section-index">02</p><h2>文书预览与编辑</h2></div>
          <span v-if="selectedDraft" class="subtle-chip mono">v{{ selectedDraft.version }}</span>
        </div>

        <template v-if="selectedDraft">
          <p class="panel-note">本草稿按法学已核对标注整理，定位指向本次上传材料；字段映射仍待法学会签，不作为正式法律文书。</p>

          <div v-if="!editing" class="draft-preview">
            <pre class="draft-body">{{ selectedDraft.body || '（空草稿）' }}</pre>
          </div>
          <div v-else class="draft-edit">
            <textarea v-model="draftBody" rows="18" placeholder="在此编辑文书正文…" />
          </div>

          <p v-if="hasPlaceholder" class="notice notice-warning" role="note">
            <strong>正文含未解析占位</strong>
            <span>请补齐【…】或双大括号占位后才能提交人工复核或下载。</span>
          </p>
          <p v-if="saveError" class="notice notice-error" role="alert">{{ saveError }}</p>

          <div class="action-box">
            <p v-if="!editing">版本 v{{ selectedDraft.version }} · 上次更新 {{ formatTime(selectedDraft.updatedAt) }}</p>
            <p v-else>保存后版本自动 +1。</p>
            <div class="draft-actions">
              <template v-if="!editing">
                <button class="button button-quiet" type="button" @click="startEdit">编辑正文</button>
                <button
                  class="button button-quiet"
                  type="button"
                  :disabled="downloading || !canDownloadManual"
                  @click="downloadManual"
                >
                  {{ downloading ? '准备下载…' : '下载辅助稿（Word）' }}
                </button>
                <button
                  class="button button-primary"
                  type="button"
                  :disabled="submitting || !canSubmit"
                  @click="submitReview"
                >
                  {{ submitting ? '提交中…' : '提交人工复核' }}
                </button>
              </template>
              <template v-else>
                <button class="button button-quiet" type="button" :disabled="saving" @click="cancelEdit">取消</button>
                <button class="button button-primary" type="button" :disabled="saving" @click="save">
                  {{ saving ? '保存中…' : '保存正文' }}
                </button>
              </template>
            </div>
          </div>

          <p v-if="submitError" class="notice notice-error" role="alert">{{ submitError }}</p>
          <p v-if="downloadError" class="notice notice-error" role="alert">{{ downloadError }}</p>
          <p v-if="submitOk" class="notice notice-success" role="status">{{ submitOk }}</p>
        </template>

        <div v-else class="empty-state">
          <strong>尚未选择文书</strong>
          <p>从左侧选择一份草稿，或新建一份文书。</p>
        </div>
      </section>

      <section class="panel">
        <div class="panel-heading">
          <div><p class="section-index">03</p><h2>模板渲染</h2></div>
          <span v-if="renderedMeta" class="subtle-chip mono">{{ renderedMeta.docType }} · v{{ renderedMeta.version }}</span>
        </div>
        <p class="panel-note">按已会签模板与已确认事实快照渲染文书；上游模块结论自动代入。结果须人工复核，不作为正式法律文书。</p>

        <form class="form-stack create-row" @submit.prevent="renderDraft">
          <label>
            <span>文书类型（docType）</span>
            <input v-model="renderDocType" placeholder="如 indictment-assist" />
          </label>
          <button class="button button-primary" type="submit" :disabled="rendering || !renderDocType.trim()">
            {{ rendering ? '渲染中…' : '渲染文书' }}
          </button>
        </form>
        <p v-if="renderError" class="notice notice-error" role="alert">{{ renderError }}</p>

        <template v-if="renderedMeta">
          <dl class="data-list inline-data">
            <div><dt>状态</dt><dd>{{ renderedMeta.outcomeStatus }}</dd></div>
            <div><dt>文书类型</dt><dd class="mono">{{ renderedMeta.docType }}</dd></div>
            <div><dt>工件版本</dt><dd class="mono">v{{ renderedMeta.version }}</dd></div>
          </dl>
          <div v-if="renderedBody" class="draft-preview">
            <pre class="draft-body">{{ renderedBody }}</pre>
          </div>
          <p v-else class="notice notice-warning" role="note">
            渲染被阻断，未产出正文（存在未解析占位或缺失输入）。
          </p>
          <div v-if="renderedMeta" class="draft-actions">
            <button
              class="button button-quiet"
              type="button"
              :disabled="downloading || !canDownloadRendered"
              @click="downloadRendered"
            >
              {{ downloading ? '准备下载…' : '下载辅助稿（Word）' }}
            </button>
          </div>
          <p v-if="downloadError" class="notice notice-error" role="alert">{{ downloadError }}</p>
        </template>
        <div v-else class="empty-state">
          <strong>尚无渲染结果</strong>
          <p>需事实已确认、模板与上游模块结论已具备；渲染结果留痕并须人工复核。</p>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.documents-layout {
  display: grid;
  grid-template-columns: minmax(300px, .8fr) minmax(0, 1.2fr);
  gap: 24px;
  align-items: start;
}
.create-row {
  margin-bottom: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--lc-line);
}
.draft-row {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 15px 8px;
  border: 0;
  border-bottom: 1px solid var(--lc-line);
  background: none;
  text-align: left;
  cursor: pointer;
  font: inherit;
}
.draft-row:hover { background: var(--lc-surface-alt); }
.draft-row.is-active { background: var(--lc-brand-100); }
.chip-pending {
  color: #815000;
  background: var(--lc-review-soft);
  border-color: var(--lc-review);
}
.draft-body {
  margin: 0;
  padding: 16px;
  min-height: 320px;
  color: var(--lc-ink);
  background: var(--lc-surface-alt);
  border: 1px solid var(--lc-line);
  border-radius: 6px;
  font-size: 13px;
  line-height: 1.8;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.draft-edit textarea {
  min-height: 320px;
  font-size: 13px;
  line-height: 1.7;
}
.draft-actions {
  display: flex;
  gap: 10px;
}
@media (max-width: 900px) {
  .documents-layout { grid-template-columns: 1fr; }
}
</style>
