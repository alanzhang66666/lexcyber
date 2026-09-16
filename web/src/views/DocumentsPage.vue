<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import type { CaseView, DraftView } from '../api-types'
import { isPlaceholderCaseId } from '../data/placeholder-cases'
import { rememberT1Case } from '../lib/current-case'

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

const workspaceTo = computed(() => (caseItem.value ? `/cases/${caseItem.value.id}` : '/cases'))
const selectedDraft = computed(() => drafts.value.find((d) => d.id === selectedId.value) ?? null)
const bodyEmpty = computed(() => !(selectedDraft.value?.body ?? '').trim())
const hasPlaceholder = computed(() => /【待补充】/.test(selectedDraft.value?.body ?? ''))
const canSubmit = computed(() => Boolean(selectedDraft.value) && !bodyEmpty.value && !hasPlaceholder.value)

function formatTime(value?: string | null) {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(d)
}

async function loadCase() {
  loading.value = true
  error.value = ''
  caseItem.value = null
  drafts.value = []
  if (!caseId.value || isPlaceholderCaseId(caseId.value)) {
    loading.value = false
    return
  }
  try {
    caseItem.value = await api.getCase(caseId.value)
    rememberT1Case(caseItem.value.id)
    await loadDrafts()
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '案件读取失败。'
  } finally {
    loading.value = false
  }
}

async function loadDrafts() {
  const list = await api.listCaseDrafts(caseId.value)
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
  saving.value = true
  saveError.value = ''
  try {
    const updated = await api.putCaseDraft(caseId.value, selectedDraft.value.id, {
      body: draftBody.value,
      version: selectedDraft.value.version,
    })
    const index = drafts.value.findIndex((d) => d.id === updated.id)
    if (index >= 0) drafts.value[index] = updated
    else drafts.value.push(updated)
    selectedId.value = updated.id
    editing.value = false
  } catch (caught) {
    saveError.value = caught instanceof Error ? caught.message : '保存失败。'
  } finally {
    saving.value = false
  }
}

async function create() {
  const type = newType.value.trim()
  if (!type) return
  creating.value = true
  createError.value = ''
  try {
    const draft = await api.createCaseDraft(caseId.value, { draftType: type, body: '' })
    drafts.value = [draft, ...drafts.value]
    selectedId.value = draft.id
    newType.value = ''
    editing.value = false
  } catch (caught) {
    createError.value = caught instanceof Error ? caught.message : '新建失败。'
  } finally {
    creating.value = false
  }
}

async function submitReview() {
  if (!selectedDraft.value || !canSubmit.value) return
  submitting.value = true
  submitError.value = ''
  submitOk.value = ''
  try {
    await api.openCaseReview(caseId.value, {
      module: 'sentencing',
      draftId: selectedDraft.value.id,
      draftVersion: selectedDraft.value.version,
    })
    submitOk.value = '已提交人工复核。'
  } catch (caught) {
    submitError.value = caught instanceof Error ? caught.message : '提交复核失败。'
  } finally {
    submitting.value = false
  }
}

onMounted(() => void loadCase())
</script>

<template>
  <div class="page-stack">
    <header class="page-heading">
      <div>
        <RouterLink class="back-link" :to="workspaceTo">← 返回案件工作区</RouterLink>
        <p class="eyebrow">文书辅助</p>
        <h1>文书辅助</h1>
        <p>{{ caseItem?.title || '未接通案件' }} · 文书草稿的预览、编辑、保存与版本管理</p>
      </div>
    </header>

    <div v-if="loading" class="panel empty-state" aria-live="polite">正在读取案件与文书草稿…</div>

    <div v-else-if="error" class="panel">
      <p class="notice notice-error" role="alert">{{ error }}</p>
      <button class="button button-quiet" type="button" @click="loadCase">重试</button>
    </div>

    <div v-else-if="isPlaceholderCaseId(caseId)" class="panel empty-state">
      <strong>请先选择真实案件</strong>
      <p>文书草稿挂在具体案件下，示例案件不适用。</p>
      <RouterLink class="button button-primary" to="/cases">前往案件中心</RouterLink>
    </div>

    <div v-else class="documents-layout">
      <section class="panel">
        <div class="panel-heading">
          <div><p class="section-index">01</p><h2>文书列表</h2></div>
          <button class="button button-quiet" type="button" :disabled="loading" @click="loadDrafts">刷新</button>
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
          <p class="panel-note">正文格式（纯文本 / Markdown）待 T1/T3 确认，暂以纯文本展示与编辑。</p>

          <div v-if="!editing" class="draft-preview">
            <pre class="draft-body">{{ selectedDraft.body || '（空草稿）' }}</pre>
          </div>
          <div v-else class="draft-edit">
            <textarea v-model="draftBody" rows="18" placeholder="在此编辑文书正文…" />
          </div>

          <p v-if="hasPlaceholder" class="notice notice-warning" role="note">
            <strong>正文含【待补充】占位</strong>
            <span>补齐占位后才能提交人工复核。</span>
          </p>
          <p v-if="saveError" class="notice notice-error" role="alert">{{ saveError }}</p>

          <div class="action-box">
            <p v-if="!editing">版本 v{{ selectedDraft.version }} · 上次更新 {{ formatTime(selectedDraft.updatedAt) }}</p>
            <p v-else>保存后版本自动 +1。</p>
            <div class="draft-actions">
              <template v-if="!editing">
                <button class="button button-quiet" type="button" @click="startEdit">编辑正文</button>
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
          <p v-if="submitOk" class="notice notice-success" role="status">{{ submitOk }}</p>
        </template>

        <div v-else class="empty-state">
          <strong>尚未选择文书</strong>
          <p>从左侧选择一份草稿，或新建一份文书。</p>
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
