<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { apiV2 } from '../api'
import type { FactItem, FactsDiffView, FactsVersionView } from '../api-types'
import { isExtractedFactKey } from '../lib/extract-candidates'
import LocatorChip from './LocatorChip.vue'
import VerificationBadge from './VerificationBadge.vue'

const props = defineProps<{ caseId: string }>()
const emit = defineEmits<{ locate: [documentId: string | undefined, locator: string] }>()

type FactsPanelView = {
  items: FactItem[]
  status: 'draft' | 'confirmed'
  confirmedAt?: string | null
}

const loading = ref(true)
const error = ref('')
const facts = ref<FactsPanelView | null>(null)

const editing = ref(false)
const draft = ref<FactItem[]>([])
const saving = ref(false)
const saveError = ref('')
const confirming = ref(false)
const confirmError = ref('')
const versions = ref<FactsVersionView[]>([])
const selectedVersionId = ref('')
const againstVersionId = ref('')
const diff = ref<FactsDiffView | null>(null)
const versionLoading = ref(false)
const versionError = ref('')
const cloning = ref(false)
const workCopyDirty = ref(false)
let loadGeneration = 0
let comparisonGeneration = 0

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`
  if (value && typeof value === 'object') {
    return `{${Object.keys(value as Record<string, unknown>).sort().map((key) => `${JSON.stringify(key)}:${canonical((value as Record<string, unknown>)[key])}`).join(',')}}`
  }
  return JSON.stringify(value)
}

function sameFactsPayload(entities: Record<string, unknown>, payload: unknown): boolean {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return false
  const snapshot = payload as Record<string, unknown>
  return canonical({ items: entities.items ?? [], entities: entities.entities ?? {} })
    === canonical({ items: snapshot.items ?? [], entities: snapshot.entities ?? {} })
}

function formatTime(value?: string | null) {
  return value ? new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : '—'
}

const reviewedItems = computed(() => (facts.value?.items ?? []).filter((item) => !isExtractedFactKey(item.key)))

async function load() {
  const generation = ++loadGeneration
  const caseId = props.caseId
  loading.value = true
  error.value = ''
  try {
    const [entities, head, history] = await Promise.all([
      apiV2.getFactsEntities(caseId),
      apiV2.getFactsHead(caseId),
      apiV2.listFactsVersions(caseId),
    ])
    if (generation !== loadGeneration || props.caseId !== caseId) return
    const items = (entities.items ?? []) as FactItem[]
    const confirmedId = (head.confirmedFactsVersionId ?? null) as string | null
    let matchesConfirmed = false
    if (confirmedId) {
      try {
        const confirmed = await apiV2.getFactsVersion(caseId, confirmedId)
        if (generation !== loadGeneration || props.caseId !== caseId) return
        matchesConfirmed = sameFactsPayload(entities, confirmed.payload)
      } catch {
        // 无法读取基线时保守要求重新建版确认，避免误标已确认。
      }
    }
    if (generation !== loadGeneration || props.caseId !== caseId) return
    facts.value = {
      items,
      status: confirmedId ? 'confirmed' : 'draft',
      confirmedAt: (head.updatedAt ?? null) as string | null,
    }
    versions.value = (history.items ?? []) as FactsVersionView[]
    const confirmed = versions.value.find((item) => item.factsVersionId === confirmedId)
    selectedVersionId.value = confirmed?.factsVersionId ?? versions.value[0]?.factsVersionId ?? ''
    againstVersionId.value = versions.value.find((item) => item.factsVersionId !== selectedVersionId.value)?.factsVersionId ?? ''
    workCopyDirty.value = Boolean(confirmedId && !matchesConfirmed)
  } catch (caught) {
    if (generation === loadGeneration && props.caseId === caseId) {
      error.value = caught instanceof Error ? caught.message : '事实读取失败。'
    }
  } finally {
    if (generation === loadGeneration) loading.value = false
  }
}

async function compareVersions() {
  if (!selectedVersionId.value || !againstVersionId.value || selectedVersionId.value === againstVersionId.value) return
  versionLoading.value = true
  versionError.value = ''
  diff.value = null
  const request = ++comparisonGeneration
  const generation = loadGeneration
  const caseId = props.caseId
  const fromVersionId = selectedVersionId.value
  const againstId = againstVersionId.value
  try {
    const loaded = await apiV2.diffFactsVersion(caseId, fromVersionId, againstId)
    if (request === comparisonGeneration && generation === loadGeneration && props.caseId === caseId
      && selectedVersionId.value === fromVersionId && againstVersionId.value === againstId) diff.value = loaded
  } catch (caught) {
    if (request === comparisonGeneration && generation === loadGeneration && props.caseId === caseId) {
      versionError.value = caught instanceof Error ? caught.message : '版本对比失败。'
    }
  } finally {
    if (request === comparisonGeneration) versionLoading.value = false
  }
}

async function cloneVersion() {
  if (!selectedVersionId.value || editing.value || saving.value || confirming.value || cloning.value) return
  cloning.value = true
  versionError.value = ''
  const generation = loadGeneration
  const caseId = props.caseId
  try {
    await apiV2.cloneFactsVersion(caseId, selectedVersionId.value)
    await load()
  } catch (caught) {
    if (generation === loadGeneration && props.caseId === caseId) {
      versionError.value = caught instanceof Error ? caught.message : '版本回写工作副本失败。'
    }
  } finally {
    if (props.caseId === caseId) cloning.value = false
  }
}

function versionLabel(version: FactsVersionView) {
  return `v${version.version} · ${version.status} · ${version.factsVersionId}`
}

function diffEntries(section: { added: Record<string, unknown>[]; removed: Record<string, unknown>[]; changed: Record<string, unknown>[] }) {
  return [
    ...section.added.map((item) => ({ kind: '新增', item })),
    ...section.removed.map((item) => ({ kind: '移除', item })),
    ...section.changed.map((item) => ({ kind: '变更', item })),
  ]
}

function startEdit() {
  if (saving.value || confirming.value || cloning.value) return
  draft.value = (facts.value?.items ?? []).map((item) => ({ ...item }))
  editing.value = true
  saveError.value = ''
  confirmError.value = ''
}

function cancelEdit() {
  editing.value = false
  draft.value = []
}

function addItem() {
  draft.value.push({ key: '', value: '', locator: '' })
}

function removeItem(index: number) {
  draft.value.splice(index, 1)
}

async function save() {
  if (!editing.value || saving.value || confirming.value || cloning.value) return
  const caseId = props.caseId
  saving.value = true
  saveError.value = ''
  try {
    const items = draft.value
      .map((item) => ({ ...item, key: item.key.trim(), value: item.value.trim(), locator: item.locator?.trim() || null }))
      .filter((item) => item.key && item.value)
    await apiV2.replaceFactsEntities(caseId, 'facts', items)
    if (props.caseId !== caseId) return
    await load()
    editing.value = false
  } catch (caught) {
    if (props.caseId === caseId) saveError.value = caught instanceof Error ? caught.message : '事实保存失败。'
  } finally {
    if (props.caseId === caseId) saving.value = false
  }
}

async function confirm() {
  if (confirming.value || saving.value || cloning.value) return
  const caseId = props.caseId
  confirming.value = true
  confirmError.value = ''
  try {
    // /v2 语义：固化工作副本为新 FactsVersion，再按预期 head CAS 确认
    const head = await apiV2.getFactsHead(caseId)
    if (props.caseId !== caseId) return
    const expected = (head.confirmedFactsVersionId ?? null) as string | null
    const created = await apiV2.createFactsVersion(caseId)
    if (props.caseId !== caseId) return
    const versionId = String(created.factsVersionId ?? created.facts_version_id ?? '')
    await apiV2.confirmFactsVersion(caseId, versionId, expected)
    if (props.caseId !== caseId) return
    await load()
  } catch (caught) {
    if (props.caseId === caseId) confirmError.value = caught instanceof Error ? caught.message : '事实确认失败。'
  } finally {
    if (props.caseId === caseId) confirming.value = false
  }
}

function resetForCase() {
  loadGeneration += 1
  loading.value = true
  error.value = ''
  facts.value = null
  versions.value = []
  selectedVersionId.value = ''
  againstVersionId.value = ''
  diff.value = null
  comparisonGeneration += 1
  versionLoading.value = false
  versionError.value = ''
  workCopyDirty.value = false
  editing.value = false
  draft.value = []
  saving.value = false
  confirming.value = false
  cloning.value = false
}

watch(() => props.caseId, () => {
  resetForCase()
  void load()
})

watch([selectedVersionId, againstVersionId], () => {
  comparisonGeneration += 1
  versionLoading.value = false
})

onMounted(() => void load())
</script>

<template>
  <article class="panel">
    <div class="panel-heading">
      <div>
        <p class="section-index">04</p>
        <h2>已核对事实</h2>
      </div>
      <span class="subtle-chip" :class="{ 'chip-confirmed': facts?.status === 'confirmed' && !workCopyDirty }">
        {{ facts?.status === 'confirmed' && !workCopyDirty ? '已确认基线' : workCopyDirty ? '工作副本待建版确认' : '工作副本草稿' }}
      </span>
    </div>

    <div v-if="loading" class="empty-state" aria-live="polite">正在读取事实…</div>
    <p v-else-if="error" class="notice notice-error" role="alert">
      {{ error }}
      <button class="text-button" type="button" @click="load">重试</button>
    </p>

    <template v-else-if="facts">
      <p class="panel-note">下列条目来自当前工作副本；仅已确认基线代表已核对标注，工作副本修改后需建版确认。</p>
      <p v-if="facts.confirmedAt" class="panel-note">已于 {{ formatTime(facts.confirmedAt) }} 确认。</p>

      <section class="version-history" aria-label="事实版本历史">
        <div class="subsection-heading">
          <div><h3>事实版本历史</h3><p class="panel-note">版本不可变；回写只更新工作副本，仍需建版并确认后才推进 head。</p></div>
        </div>
        <div v-if="!versions.length" class="empty-state">暂无已固化事实版本。</div>
        <template v-else>
          <div class="version-controls">
            <label>
              <span>当前版本</span>
              <select v-model="selectedVersionId">
                <option v-for="version in versions" :key="version.factsVersionId" :value="version.factsVersionId">{{ versionLabel(version) }}</option>
              </select>
            </label>
            <label>
              <span>对比基准</span>
              <select v-model="againstVersionId">
                <option value="">请选择版本</option>
                <option v-for="version in versions" :key="version.factsVersionId" :value="version.factsVersionId">{{ versionLabel(version) }}</option>
              </select>
            </label>
            <div class="version-actions">
              <button class="button button-quiet" type="button" :disabled="versionLoading || !againstVersionId || selectedVersionId === againstVersionId" @click="compareVersions">
                {{ versionLoading ? '对比中…' : '对比版本' }}
              </button>
              <button class="button button-quiet" type="button" :disabled="cloning || saving || confirming || editing || !selectedVersionId" @click="cloneVersion">
                {{ cloning ? '回写中…' : '回写为工作副本' }}
              </button>
            </div>
          </div>
          <p v-if="versionError" class="notice notice-error" role="alert">{{ versionError }}</p>
          <div v-if="diff" class="diff-result">
            <strong>版本对比：{{ diff.fromFactsVersionId }} → {{ diff.toFactsVersionId }}</strong>
            <div v-for="(section, name) in diff.sections" :key="name" class="diff-section">
              <h4>{{ name }}</h4>
              <ul v-if="diffEntries(section).length">
                <li v-for="(entry, i) in diffEntries(section)" :key="i"><span>{{ entry.kind }}</span> <code>{{ JSON.stringify(entry.item) }}</code></li>
              </ul>
              <p v-else class="panel-note">无变化</p>
            </div>
          </div>
        </template>
      </section>

      <!-- 只读列表 -->
      <dl v-if="!editing" class="data-list">
        <div v-for="(item, i) in reviewedItems" :key="item.id ?? i">
          <dt>{{ item.key }}</dt>
          <dd>
            {{ item.value }}
            <VerificationBadge v-if="item.verificationStatus" :status="item.verificationStatus" />
            <LocatorChip v-if="item.locator" :locator="item.locator" @locate="(l) => emit('locate', item.sourceDocumentId ?? undefined, l)" />
          </dd>
        </div>
        <div v-if="!reviewedItems.length" class="empty-state">
          <strong>暂无已核对事实</strong>
          <p>解析完成后由法学标注写入；也可在此人工录入后确认。</p>
        </div>
      </dl>

      <!-- 编辑态 -->
      <div v-else class="fact-edit">
        <div v-for="(item, i) in draft" :key="i" class="fact-row">
          <input v-model="item.key" placeholder="事实名称，如 涉案金额" />
          <input v-model="item.value" placeholder="事实内容" />
          <input v-model="item.locator" placeholder="定位，如 paragraph:2" />
          <button class="button button-quiet" type="button" @click="removeItem(i)">删除</button>
        </div>
        <button class="text-button" type="button" :disabled="saving || confirming || cloning" @click="addItem">＋ 添加事实</button>
        <p v-if="saveError" class="notice notice-error" role="alert">{{ saveError }}</p>
        <div class="action-box">
          <button class="button button-quiet" type="button" :disabled="saving" @click="cancelEdit">取消</button>
          <button class="button button-primary" type="button" :disabled="saving || confirming || cloning" @click="save">
            {{ saving ? '保存中…' : '保存草稿' }}
          </button>
        </div>
      </div>

      <p v-if="confirmError" class="notice notice-error" role="alert">{{ confirmError }}</p>

      <!-- 草稿态的操作 -->
      <div v-if="!editing && (facts.status !== 'confirmed' || workCopyDirty)" class="action-box">
        <button class="button button-quiet" type="button" :disabled="saving || confirming || cloning" @click="startEdit">编辑事实</button>
        <button
          class="button button-primary"
          type="button"
          :disabled="confirming || saving || cloning || editing || !facts.items.length"
          @click="confirm"
        >
          {{ confirming ? '确认中…' : '确认事实' }}
        </button>
      </div>
    </template>
  </article>
</template>

<style scoped>
.chip-confirmed {
  color: #086b62;
  background: var(--lc-evidence-soft);
  border-color: var(--lc-evidence);
}
.version-history {
  display: grid;
  gap: 12px;
  margin: 18px 0;
  padding: 14px;
  border: 1px solid var(--lc-line);
  border-radius: 8px;
}
.subsection-heading h3 {
  margin: 0;
  color: var(--lc-brand-900);
  font-size: 14px;
}
.subsection-heading p {
  margin: 4px 0 0;
}
.version-controls {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto;
  gap: 10px;
  align-items: end;
}
.version-controls label {
  display: grid;
  gap: 5px;
  color: var(--lc-muted);
  font-size: 12px;
}
.version-controls select {
  min-width: 0;
  padding: 8px;
  border: 1px solid var(--lc-line);
  border-radius: 6px;
  background: var(--lc-surface);
  color: var(--lc-ink);
  font: inherit;
}
.version-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.diff-result {
  display: grid;
  gap: 10px;
  padding-top: 8px;
  border-top: 1px solid var(--lc-line);
  font-size: 12px;
}
.diff-section h4 {
  margin: 0 0 4px;
  color: var(--lc-brand-900);
}
.diff-section ul {
  margin: 0;
  padding-left: 18px;
}
.diff-section code {
  overflow-wrap: anywhere;
}
@media (max-width: 900px) {
  .version-controls {
    grid-template-columns: 1fr;
  }
}
.fact-edit {
  display: grid;
  gap: 12px;
}
.fact-row {
  display: grid;
  grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.4fr) minmax(0, 0.9fr) auto;
  gap: 8px;
  align-items: center;
}
@media (max-width: 1023px) {
  .fact-row {
    grid-template-columns: 1fr;
  }
}
.fact-row input {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid var(--lc-line);
  border-radius: 6px;
  color: var(--lc-ink);
  background: var(--lc-surface);
  font: inherit;
  font-size: 13px;
}
.fact-row input:focus {
  outline: 3px solid var(--lc-focus);
  outline-offset: 1px;
}
</style>
