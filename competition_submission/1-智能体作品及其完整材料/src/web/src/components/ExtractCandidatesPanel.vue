<script setup lang="ts">
import type { ExtractGroup } from '../lib/extract-candidates'
import LocatorChip from './LocatorChip.vue'

defineProps<{ groups: ExtractGroup[] }>()
const emit = defineEmits<{ locate: [documentId: string | undefined, locator: string] }>()

const KIND_LABEL: Record<string, string> = {
  date: '日期',
  amount: '金额',
}
</script>

<template>
  <article v-if="groups.length" class="panel">
    <div class="panel-heading">
      <div>
        <p class="section-index">02b</p>
        <h2>材料抽取候选</h2>
      </div>
      <span class="subtle-chip">启发式对照</span>
    </div>
    <p class="panel-note">从本次上传材料的解析正文中抽出日期与金额，仅供对照；不是已核对事实，也不是系统结论。</p>
    <div v-for="group in groups" :key="group.documentId" class="extract-group">
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
</style>
