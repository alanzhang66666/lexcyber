<script setup lang="ts">
import { computed } from 'vue'
import type { CandidatePath, CandidatePathKind, EvidenceRef } from '../api-types'
import LocatorChip from './LocatorChip.vue'
import VerificationBadge from './VerificationBadge.vue'

/**
 * 候选路径卡：候选/替代/排除路径，支持证据与相反证据**并列**展示。
 * 即使某一方为空也保留该栏并显示「暂无」，不得只显示支持一方。
 */
const props = defineProps<{ path: CandidatePath }>()
const emit = defineEmits<{ locate: [locator: string] }>()

const KIND_LABELS: Record<CandidatePathKind, string> = {
  candidate: '候选路径',
  alternative: '替代路径',
  excluded: '已排除路径',
}

const kindLabel = computed(() => (props.path.kind ? KIND_LABELS[props.path.kind] : '候选路径'))
const kindClass = computed(() => ({
  'path-excluded': props.path.kind === 'excluded',
  'path-alternative': props.path.kind === 'alternative',
}))

function evidenceKey(e: EvidenceRef, i: number) {
  return e.id ?? e.locator ?? i
}
</script>

<template>
  <article class="path-card" :class="{ 'path-excluded': path.kind === 'excluded' }">
    <header class="path-head">
      <div class="path-title">
        <span class="path-kind" :class="kindClass">{{ kindLabel }}</span>
        <h3>{{ path.title }}</h3>
      </div>
      <VerificationBadge :status="path.status" />
    </header>

    <p v-if="path.summary" class="path-summary">{{ path.summary }}</p>

    <div class="evidence-grid">
      <section class="evidence-col">
        <h4 class="evidence-title support">支持证据</h4>
        <ul v-if="path.supporting?.length" class="evidence-list">
          <li v-for="(e, i) in path.supporting" :key="evidenceKey(e, i)">
            <span v-if="e.quote" class="evidence-quote">{{ e.quote }}</span>
            <LocatorChip v-if="e.locator" :locator="e.locator" @locate="(l) => emit('locate', l)" />
            <code v-if="!e.quote && !e.locator && e.id" class="evidence-ref">{{ e.id }}</code>
            <span v-if="!e.quote && !e.locator && !e.id" class="evidence-empty">—</span>
          </li>
        </ul>
        <p v-else class="evidence-empty">暂无</p>
      </section>

      <section class="evidence-col">
        <h4 class="evidence-title contrary">相反证据</h4>
        <ul v-if="path.contrary?.length" class="evidence-list">
          <li v-for="(e, i) in path.contrary" :key="evidenceKey(e, i)">
            <span v-if="e.quote" class="evidence-quote">{{ e.quote }}</span>
            <LocatorChip v-if="e.locator" :locator="e.locator" @locate="(l) => emit('locate', l)" />
            <code v-if="!e.quote && !e.locator && e.id" class="evidence-ref">{{ e.id }}</code>
            <span v-if="!e.quote && !e.locator && !e.id" class="evidence-empty">—</span>
          </li>
        </ul>
        <p v-else class="evidence-empty">暂无</p>
      </section>
    </div>
  </article>
</template>

<style scoped>
.path-card {
  display: grid;
  gap: 12px;
  padding: 16px;
  background: var(--lc-surface);
  border: 1px solid var(--lc-line);
  border-radius: 8px;
}
.path-card.path-excluded {
  background: var(--lc-surface-alt);
  opacity: 0.86;
}
.path-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.path-title {
  display: grid;
  gap: 6px;
  min-width: 0;
}
.path-title h3 {
  margin: 0;
  color: var(--lc-brand-900);
  font-size: 15px;
}
.path-kind {
  width: fit-content;
  padding: 2px 10px;
  color: var(--lc-brand-800);
  background: var(--lc-brand-100);
  border-radius: 999px;
  font-size: 11px;
  font-weight: 750;
}
.path-kind.path-alternative {
  color: #815000;
  background: var(--lc-review-soft);
}
.path-kind.path-excluded {
  color: var(--lc-muted);
  background: var(--lc-surface-alt);
}
.path-summary {
  margin: 0;
  color: var(--lc-ink);
  font-size: 13px;
  line-height: 1.7;
}
.evidence-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.evidence-col {
  min-width: 0;
  padding: 12px;
  background: var(--lc-surface-alt);
  border: 1px solid var(--lc-line);
  border-radius: 6px;
}
.evidence-title {
  margin: 0 0 8px;
  font-size: 12px;
}
.evidence-title.support {
  color: var(--lc-evidence);
}
.evidence-title.contrary {
  color: var(--lc-risk);
}
.evidence-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 8px;
}
.evidence-list li {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.evidence-quote {
  color: var(--lc-ink);
  font-size: 12px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}
.evidence-ref {
  color: var(--lc-muted);
  font-family: var(--lc-mono, ui-monospace, monospace);
  font-size: 11px;
}
.evidence-empty {
  margin: 0;
  color: var(--lc-muted);
  font-size: 12px;
}
@media (max-width: 640px) {
  .evidence-grid {
    grid-template-columns: 1fr;
  }
}
</style>
