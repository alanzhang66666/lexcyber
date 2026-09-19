<script setup lang="ts">
import { computed, ref } from 'vue'
import type { ExtractGroup } from '../lib/extract-candidates'
import LocatorChip from './LocatorChip.vue'

const props = defineProps<{ groups: ExtractGroup[] }>()
const emit = defineEmits<{ locate: [documentId: string | undefined, locator: string] }>()

const KIND_LABEL: Record<string, string> = {
  date: '日期',
  amount: '金额',
}
const PREVIEW = 4
const expanded = ref(false)
const total = computed(() => props.groups.reduce((sum, group) => sum + group.candidates.length, 0))
const visibleGroups = computed(() => {
  if (expanded.value) return props.groups
  let remaining = PREVIEW
  return props.groups.flatMap((group) => {
    if (remaining <= 0) return []
    const candidates = group.candidates.slice(0, remaining)
    remaining -= candidates.length
    return [{ ...group, candidates }]
  })
})
</script>

<template>
  <article v-if="groups.length" class="panel">
    <div class="panel-heading">
      <div>
        <p class="section-index">03</p>
        <h2>材料抽取候选</h2>
      </div>
      <span class="subtle-chip">启发式对照 · {{ total }} 条</span>
    </div>
    <p class="panel-note">从本次上传材料的解析正文中抽出日期与金额，仅供对照；不是已核对事实。</p>
    <div v-for="group in visibleGroups" :key="group.documentId" class="extract-group">
      <h3>{{ group.filename }}</h3>
      <dl class="data-list">
        <div v-for="(item, index) in group.candidates" :key="`${item.kind}-${item.value}-${index}`">
          <dt>{{ KIND_LABEL[item.kind] || item.kind }}</dt>
          <dd>
            {{ item.value }}
            <LocatorChip
              v-if="item.locator"
              :locator="item.locator"
              @locate="(locator) => emit('locate', group.documentId, locator)"
            />
          </dd>
        </div>
      </dl>
    </div>
    <button
      v-if="total > PREVIEW"
      class="text-button"
      type="button"
      @click="expanded = !expanded"
    >
      {{ expanded ? '收起候选' : `显示全部 ${total} 条` }}
    </button>
  </article>
</template>

<style scoped>
.extract-group {
  display: grid;
  gap: 8px;
}
.extract-group + .extract-group {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--lc-line);
}
.extract-group h3 {
  margin: 0;
  color: var(--lc-ink);
  font-size: 13px;
  font-weight: 700;
}
.text-button {
  margin-top: 8px;
}
</style>
