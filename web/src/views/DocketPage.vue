<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import type { CaseView, DocumentView } from '../api-types'
import CasePhaseBar from '../components/CasePhaseBar.vue'
import DocumentParseResult from '../components/DocumentParseResult.vue'
import PlaceholderBanner from '../components/PlaceholderBanner.vue'
import { isPlaceholderCaseId } from '../data/placeholder-cases'
import { rememberT1Case } from '../lib/current-case'

const route = useRoute()
const caseId = computed(() => String(route.params.caseId || ''))
const loading = ref(true)
const error = ref('')
const caseItem = ref<CaseView | null>(null)
const documents = ref<DocumentView[]>([])
const selectedId = ref('')
const parseContent = ref<unknown>(null)
const parseLoading = ref(false)
const parseError = ref('')
const targetLocator = computed(() => {
  const v = route.query.locator
  return typeof v === 'string' && v ? v : null
})

const workspaceTo = computed(() => (caseItem.value ? `/cases/${caseItem.value.id}` : '/cases'))
const analysisTo = computed(() => (caseItem.value ? `/cases/${caseItem.value.id}/analysis` : '/cases'))
const selected = computed(() => documents.value.find((d) => d.id === selectedId.value) ?? null)

const PARSE_STATUS_LABEL: Record<string, string> = {
  not_started: '未解析',
  queued: '排队中',
  running: '解析中',
  completed: '已解析',
  failed: '解析失败',
  timed_out: '解析超时',
  waiting_review: '待复核',
  rejected: '已拒绝',
}

function parseStatusLabel(status: string | undefined) {
  return PARSE_STATUS_LABEL[status ?? ''] ?? status ?? '—'
}

async function loadParse(doc: DocumentView) {
  parseContent.value = null
  parseError.value = ''
  if (!doc.parseTaskId) return
  parseLoading.value = true
  try {
    const payload = await api.getTaskResult(doc.parseTaskId)
    parseContent.value = payload.content
  } catch (caught) {
    parseError.value = caught instanceof Error ? caught.message : '解析结果读取失败。'
  } finally {
    parseLoading.value = false
  }
}

function selectDocument(doc: DocumentView) {
  selectedId.value = doc.id
  void loadParse(doc)
}

async function load() {
  loading.value = true
  error.value = ''
  caseItem.value = null
  documents.value = []
  selectedId.value = ''
  parseContent.value = null
  if (!caseId.value || isPlaceholderCaseId(caseId.value)) {
    loading.value = false
    return
  }
  try {
    caseItem.value = await api.getCase(caseId.value)
    rememberT1Case(caseItem.value.id)
    const page = await api.listDocuments(caseId.value, { size: 100 })
    documents.value = page.items
    const firstParsed = page.items.find((d) => d.parseStatus === 'completed' && d.parseTaskId) ?? page.items[0]
    if (firstParsed) selectDocument(firstParsed)
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '案件读取失败。'
  } finally {
    loading.value = false
  }
}

onMounted(() => void load())
watch(caseId, () => void load())
</script>

<template>
  <div class="page-stack workbench-stack">
    <PlaceholderBanner />
    <header class="workbench-header">
      <div>
        <p class="breadcrumb">案件中心 / {{ caseItem?.title || '未接通案件' }}</p>
        <h1>智能阅卷</h1>
      </div>
      <CasePhaseBar current="docket" />
      <RouterLink class="button button-primary" :to="analysisTo">进入量刑分析</RouterLink>
    </header>
    <div v-if="loading" class="panel empty-state" aria-live="polite">正在读取案件…</div>
    <div v-else-if="error" class="panel">
      <p class="notice notice-error" role="alert">{{ error }}</p>
      <button class="button button-quiet" type="button" @click="load">重试</button>
    </div>
    <template v-else>
      <section class="panel">
        <div class="panel-heading"><div><p class="section-index">01</p><h2>案件材料</h2></div></div>
        <div v-if="!documents.length" class="empty-state">
          <strong>暂无材料</strong>
          <p>请到案件工作区上传 PDF/DOCX 材料，上传后自动解析。</p>
          <RouterLink class="button button-primary" :to="workspaceTo">前往案件工作区</RouterLink>
        </div>
        <ul v-else class="record-list docket-list">
          <li v-for="doc in documents" :key="doc.id">
            <button
              type="button"
              class="docket-item"
              :class="{ 'is-active': doc.id === selectedId }"
              @click="selectDocument(doc)"
            >
              <div class="record-main">
                <span>{{ doc.filename }}</span>
                <small>{{ doc.role }} · {{ parseStatusLabel(doc.parseStatus) }}</small>
              </div>
              <span v-if="doc.parseStatus === 'completed'" class="subtle-chip">可定位</span>
            </button>
          </li>
        </ul>
      </section>

      <section v-if="selected" class="panel">
        <div class="panel-heading">
          <div><p class="section-index">02</p><h2>解析正文 · {{ selected.filename }}</h2></div>
        </div>
        <div v-if="parseLoading" class="empty-state">正在读取解析结果…</div>
        <p v-else-if="parseError" class="notice notice-error" role="alert">{{ parseError }}</p>
        <DocumentParseResult v-else-if="parseContent" :content="parseContent" :target-locator="targetLocator" />
        <div v-else class="empty-state">
          <strong>{{ parseStatusLabel(selected.parseStatus) }}</strong>
          <p v-if="selected.parseStatus === 'completed'">该材料解析结果不可读。</p>
          <p v-else>解析完成后此处展示正文与定位。</p>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.docket-list .docket-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  padding: 12px 14px;
  border: 1px solid var(--lc-line);
  border-radius: 8px;
  background: var(--lc-surface);
  text-align: left;
  cursor: pointer;
}
.docket-list .docket-item.is-active {
  border-color: var(--lc-brand-600);
  outline: 1px solid var(--lc-brand-600);
}
.docket-list .record-main {
  display: grid;
  gap: 4px;
}
</style>
