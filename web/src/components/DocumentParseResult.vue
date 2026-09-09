<script setup lang="ts">
import { computed } from 'vue'

type Paragraph = { paragraph?: number; text?: string; style?: string; locator?: string }
type Table = { table?: number; rows?: string[][]; locator?: string }
type ParseContent = {
  schemaVersion?: string
  taskType?: string
  documentId?: string
  format?: string
  text?: string
  paragraphs?: Paragraph[]
  tables?: Table[]
  warnings?: unknown[]
  missing?: unknown[]
  errors?: unknown[]
}

const props = defineProps<{ content: unknown }>()

const parsed = computed<ParseContent | null>(() => {
  const c = props.content
  if (!c || typeof c !== 'object' || Array.isArray(c)) return null
  const r = c as Record<string, unknown>
  if (!('text' in r) && !('paragraphs' in r) && !('tables' in r)) return null
  return c as ParseContent
})

const raw = computed(() => {
  const c = props.content
  if (c === null || c === undefined || c === '') return ''
  return typeof c === 'string' ? c : JSON.stringify(c, null, 2)
})

function stringify(value: unknown) {
  return typeof value === 'string' ? value : JSON.stringify(value)
}
</script>

<template>
  <div v-if="parsed" class="parse-result">
    <div class="parse-meta">
      <span v-if="parsed.schemaVersion" class="subtle-chip mono">{{ parsed.schemaVersion }}</span>
      <span v-if="parsed.format" class="subtle-chip">{{ parsed.format }}</span>
      <span v-if="parsed.documentId" class="subtle-chip mono">{{ parsed.documentId }}</span>
    </div>

    <section v-if="parsed.text" class="parse-section">
      <h3>正文</h3>
      <p class="parse-text">{{ parsed.text }}</p>
    </section>

    <section v-if="parsed.paragraphs?.length" class="parse-section">
      <h3>段落定位</h3>
      <ul class="parse-list">
        <li v-for="(p, i) in parsed.paragraphs" :key="i">
          <span class="locator-chip mono">{{ p.locator || `paragraph:${p.paragraph ?? i + 1}` }}</span>
          <div class="parse-item">
            <span class="parse-item-text">{{ p.text || '—' }}</span>
            <small v-if="p.style" class="parse-item-style">{{ p.style }}</small>
          </div>
        </li>
      </ul>
    </section>

    <section v-if="parsed.tables?.length" class="parse-section">
      <h3>表格定位</h3>
      <div v-for="(t, i) in parsed.tables" :key="i" class="parse-table">
        <span class="locator-chip mono">{{ t.locator || `table:${t.table ?? i + 1}` }}</span>
        <table v-if="t.rows?.length" class="raw-table">
          <tbody>
            <tr v-for="(row, ri) in t.rows" :key="ri">
              <td v-for="(cell, ci) in row" :key="ci">{{ cell }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <p v-if="parsed.warnings?.length" class="notice" role="note">
      <strong>告警</strong>
      <span>{{ parsed.warnings.map(stringify).join('；') }}</span>
    </p>
    <p v-if="parsed.errors?.length" class="notice notice-error" role="alert">
      <strong>错误</strong>
      <span>{{ parsed.errors.map(stringify).join('；') }}</span>
    </p>
  </div>
  <pre v-else-if="raw" class="raw-payload">{{ raw }}</pre>
</template>

<style scoped>
.parse-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}
.parse-section {
  margin-top: 20px;
}
.parse-section h3 {
  margin: 0 0 10px;
  color: var(--lc-brand-900);
  font-size: 13px;
}
.parse-text {
  margin: 0;
  white-space: pre-wrap;
  line-height: 1.8;
  color: var(--lc-ink);
}
.parse-list {
  margin: 0;
  padding: 0;
  list-style: none;
  border-top: 1px solid var(--lc-line);
}
.parse-list li {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px 8px;
  border-bottom: 1px solid var(--lc-line);
}
.locator-chip {
  flex: 0 0 auto;
  padding: 2px 8px;
  color: var(--lc-brand-800);
  background: var(--lc-brand-100);
  border-radius: 999px;
  font-size: 11px;
}
.parse-item {
  display: grid;
  gap: 2px;
  min-width: 0;
}
.parse-item-text {
  line-height: 1.7;
}
.parse-item-style {
  color: var(--lc-muted);
}
.parse-table {
  margin-top: 12px;
}
.parse-table .locator-chip {
  display: inline-block;
  margin-bottom: 6px;
}
.raw-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.raw-table td {
  border: 1px solid var(--lc-line);
  padding: 8px 10px;
  color: var(--lc-ink);
}
</style>
