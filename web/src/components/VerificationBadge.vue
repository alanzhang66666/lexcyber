<script setup lang="ts">
import { computed } from 'vue'

/**
 * 事实/证据/结论的「待核状态」徽章。
 * 支持 T3 英文枚举与文档中文取值，未知值原样展示。
 */
const props = defineProps<{ status: string | null | undefined }>()

const LABELS: Record<string, string> = {
  candidate: '待确认',
  baseline_asserted: '待法核基准',
  confirmed: '已确认',
  rejected: '已排除',
  conflicted: '存在争议',
  auto_extracted: '自动提取',
  manual_confirmed: '人工确认',
  pending: '待确认',
  unable: '无法判断',
}

const label = computed(() => LABELS[props.status ?? ''] ?? props.status ?? '待确认')

const kind = computed(() => {
  const s = props.status ?? ''
  if (s === 'confirmed' || s === 'manual_confirmed') return 'ok'
  if (s === 'conflicted' || s === 'rejected') return 'warn'
  if (s === 'baseline_asserted') return 'review'
  return 'muted'
})
</script>

<template>
  <span class="verification-badge" :class="`v-${kind}`">{{ label }}</span>
</template>

<style scoped>
.verification-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 750;
  border: 1px solid var(--lc-line);
  white-space: nowrap;
}
.v-ok { color: #086b62; background: var(--lc-evidence-soft); border-color: var(--lc-evidence); }
.v-warn { color: #991a3b; background: var(--lc-risk-soft); border-color: var(--lc-risk); }
.v-review { color: #815000; background: var(--lc-review-soft); border-color: var(--lc-review); }
.v-muted { color: var(--lc-muted); background: var(--lc-surface-alt); }
</style>
