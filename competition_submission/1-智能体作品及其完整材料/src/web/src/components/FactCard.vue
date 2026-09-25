<script setup lang="ts">
import type { AnalysisFact } from '../api-types'
import LocatorChip from './LocatorChip.vue'
import VerificationBadge from './VerificationBadge.vue'

/**
 * 事实卡：行为阶段 + 事实内容 + 待核状态 + 原文定位。
 * 同一行为人不同阶段的事实不合并，由父组件逐条循环渲染。
 */
const props = defineProps<{ fact: AnalysisFact }>()
const emit = defineEmits<{ locate: [locator: string] }>()
</script>

<template>
  <article class="fact-card">
    <header class="fact-head">
      <span v-if="fact.stage" class="stage-chip">{{ fact.stage }}</span>
      <span v-else class="stage-chip stage-none">未分阶段</span>
      <VerificationBadge :status="fact.status" />
    </header>
    <p class="fact-statement">{{ fact.statement }}</p>
    <footer v-if="fact.locator" class="fact-foot">
      <LocatorChip :locator="fact.locator" @locate="(l) => emit('locate', l)" />
    </footer>
  </article>
</template>

<style scoped>
.fact-card {
  display: grid;
  gap: 10px;
  padding: 14px 16px;
  background: var(--lc-surface);
  border: 1px solid var(--lc-line);
  border-radius: 8px;
}
.fact-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.stage-chip {
  padding: 2px 10px;
  color: var(--lc-brand-800);
  background: var(--lc-brand-100);
  border-radius: 999px;
  font-size: 11px;
  font-weight: 750;
}
.stage-none {
  color: var(--lc-muted);
  background: var(--lc-surface-alt);
}
.fact-statement {
  margin: 0;
  color: var(--lc-ink);
  font-size: 13px;
  line-height: 1.7;
}
.fact-foot {
  display: flex;
  justify-content: flex-start;
}
</style>
