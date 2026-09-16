<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
import type { FactItem, FactView } from '../api-types'
import LocatorChip from './LocatorChip.vue'

const props = defineProps<{ caseId: string }>()
const emit = defineEmits<{ locate: [documentId: string | undefined, locator: string] }>()

const loading = ref(true)
const error = ref('')
const facts = ref<FactView | null>(null)

const editing = ref(false)
const draft = ref<FactItem[]>([])
const saving = ref(false)
const saveError = ref('')
const confirming = ref(false)
const confirmError = ref('')

function formatTime(value?: string | null) {
  return value ? new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : '—'
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    facts.value = await api.getCaseFacts(props.caseId)
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '事实读取失败。'
  } finally {
    loading.value = false
  }
}

function startEdit() {
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
  saving.value = true
  saveError.value = ''
  try {
    const items = draft.value
      .map((item) => ({ ...item, key: item.key.trim(), value: item.value.trim(), locator: item.locator?.trim() || null }))
      .filter((item) => item.key && item.value)
    facts.value = await api.putCaseFacts(props.caseId, { items })
    editing.value = false
  } catch (caught) {
    saveError.value = caught instanceof Error ? caught.message : '事实保存失败。'
  } finally {
    saving.value = false
  }
}

async function confirm() {
  confirming.value = true
  confirmError.value = ''
  try {
    facts.value = await api.confirmCaseFacts(props.caseId)
  } catch (caught) {
    confirmError.value = caught instanceof Error ? caught.message : '事实确认失败。'
  } finally {
    confirming.value = false
  }
}

onMounted(() => void load())
</script>

<template>
  <article class="panel">
    <div class="panel-heading">
      <div>
        <p class="section-index">03</p>
        <h2>事实确认</h2>
      </div>
      <span class="subtle-chip" :class="{ 'chip-confirmed': facts?.status === 'confirmed' }">
        {{ facts?.status === 'confirmed' ? '已确认' : '草稿' }}
      </span>
    </div>

    <div v-if="loading" class="empty-state" aria-live="polite">正在读取事实…</div>
    <p v-else-if="error" class="notice notice-error" role="alert">
      {{ error }}
      <button class="text-button" type="button" @click="load">重试</button>
    </p>

    <template v-else-if="facts">
      <p v-if="facts.confirmedAt" class="panel-note">已于 {{ formatTime(facts.confirmedAt) }} 确认。</p>

      <!-- 只读列表 -->
      <dl v-if="!editing" class="data-list">
        <div v-for="(item, i) in facts.items" :key="item.id ?? i">
          <dt>{{ item.key }}</dt>
          <dd>
            {{ item.value }}
            <LocatorChip v-if="item.locator" :locator="item.locator" @locate="(l) => emit('locate', item.sourceDocumentId ?? undefined, l)" />
          </dd>
        </div>
        <div v-if="!facts.items.length" class="empty-state">
          <strong>暂无事实</strong>
          <p>解析或人工录入后，可在此校对并确认。</p>
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
        <button class="text-button" type="button" @click="addItem">＋ 添加事实</button>
        <p v-if="saveError" class="notice notice-error" role="alert">{{ saveError }}</p>
        <div class="action-box">
          <button class="button button-quiet" type="button" :disabled="saving" @click="cancelEdit">取消</button>
          <button class="button button-primary" type="button" :disabled="saving" @click="save">
            {{ saving ? '保存中…' : '保存草稿' }}
          </button>
        </div>
      </div>

      <p v-if="confirmError" class="notice notice-error" role="alert">{{ confirmError }}</p>

      <!-- 草稿态的操作 -->
      <div v-if="!editing && facts.status !== 'confirmed'" class="action-box">
        <button class="button button-quiet" type="button" @click="startEdit">编辑事实</button>
        <button
          class="button button-primary"
          type="button"
          :disabled="confirming || !facts.items.length"
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
