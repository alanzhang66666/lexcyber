<script setup lang="ts">
import { computed } from 'vue'
import type { CaseRelations, CaseView } from '../api-types'
import LocatorChip from './LocatorChip.vue'

const props = defineProps<{ case: CaseView | null }>()
const emit = defineEmits<{ locate: [documentId: string | undefined, locator: string] }>()

const relations = computed<CaseRelations | null>(() => {
  const metadata = props.case?.metadata
  if (!metadata || typeof metadata !== 'object' || Array.isArray(metadata)) return null
  const r = (metadata as Record<string, unknown>).relations
  if (!r || typeof r !== 'object' || Array.isArray(r)) return null
  return r as CaseRelations
})

const hasRelations = computed(() => Boolean(
  relations.value && (
    relations.value.actors?.length ||
    relations.value.organizations?.length ||
    relations.value.accounts?.length ||
    relations.value.events?.length
  ),
))

const events = computed(() =>
  [...(relations.value?.events ?? [])].sort((a, b) => (a.occurredOn ?? '').localeCompare(b.occurredOn ?? '')),
)

function actorLabel(actorId?: string) {
  if (!actorId) return ''
  return relations.value?.actors?.find((item) => item.actorId === actorId)?.label || actorId
}

function accountLabel(accountId?: string) {
  if (!accountId) return ''
  return relations.value?.accounts?.find((item) => item.accountId === accountId)?.mask || accountId
}
</script>

<template>
  <article v-if="hasRelations" class="panel">
    <div class="panel-heading">
      <div><h2>主体关系与事件时间线</h2></div>
    </div>
    <p class="panel-note">来自案件 metadata.relations，仅记录客观关系，不含主从犯等法律定性。</p>

    <div v-if="relations?.actors?.length" class="rel-group">
      <h3>行为人</h3>
      <div class="chip-row">
        <span v-for="a in relations.actors" :key="a.actorId" class="subtle-chip">
          {{ a.label || a.actorId }}<i v-if="a.roleHint"> · {{ a.roleHint }}</i>
        </span>
      </div>
    </div>

    <div v-if="relations?.organizations?.length" class="rel-group">
      <h3>组织</h3>
      <div class="chip-row">
        <span v-for="o in relations.organizations" :key="o.organizationId" class="subtle-chip">{{ o.label || o.organizationId }}</span>
      </div>
    </div>

    <div v-if="relations?.accounts?.length" class="rel-group">
      <h3>账户</h3>
      <div class="chip-row">
        <span v-for="a in relations.accounts" :key="a.accountId" class="subtle-chip">{{ a.mask || a.accountId }}</span>
      </div>
    </div>

    <div v-if="events.length" class="rel-group">
      <h3>事件时间线</h3>
      <ol class="timeline">
        <li v-for="e in events" :key="e.eventId">
          <time>{{ e.occurredOn || '—' }}</time>
          <span class="stage-chip">{{ e.stage || '事件' }}</span>
          <span class="tl-actor">{{ actorLabel(e.actorId) || '—' }}</span>
          <span v-if="e.accountId" class="tl-account">{{ accountLabel(e.accountId) }}</span>
          <LocatorChip v-if="e.locator" :locator="e.locator" @locate="(l) => emit('locate', e.documentId, l)" />
        </li>
      </ol>
    </div>
  </article>
</template>

<style scoped>
.rel-group {
  margin-top: 18px;
}
.rel-group h3 {
  margin: 0 0 8px;
  color: var(--lc-brand-900);
  font-size: 13px;
}
.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.chip-row i {
  font-style: normal;
  color: var(--lc-muted);
}
.timeline {
  margin: 0;
  padding: 0;
  list-style: none;
  border-top: 1px solid var(--lc-line);
}
.timeline li {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  padding: 10px 4px;
  border-bottom: 1px solid var(--lc-line);
  font-size: 12px;
}
.timeline time {
  color: var(--lc-muted);
  font-size: 11px;
  white-space: nowrap;
}
.stage-chip {
  padding: 2px 8px;
  color: var(--lc-brand-800);
  background: var(--lc-brand-100);
  border-radius: 999px;
  font-size: 11px;
  font-weight: 750;
}
.tl-actor {
  color: var(--lc-ink);
}
.tl-account {
  color: var(--lc-muted);
}
</style>
