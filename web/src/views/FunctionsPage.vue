<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { CaseView } from '../api-types'
import { CORE_MODULES, modulePath } from '../data/modules'
import { currentCaseId, loadT1Cases, rememberT1Case, resolveT1CaseId } from '../lib/current-case'

const cases = ref<CaseView[]>([])
const caseLoadError = ref('')
const entries = computed(() => CORE_MODULES.map((module) => ({ ...module, to: modulePath(module, currentCaseId.value) })))

function pickCase(event: Event) {
  const id = (event.target as HTMLSelectElement).value
  if (id) rememberT1Case(id)
}

onMounted(async () => {
  await resolveT1CaseId()
  try {
    cases.value = await loadT1Cases()
  } catch (caught) {
    caseLoadError.value = caught instanceof Error ? caught.message : '案件列表读取失败。'
  }
})
</script>

<template>
  <div class="page-stack">
    <header class="page-heading">
      <div>
        <p class="eyebrow">功能中心</p>
        <h1>功能中心</h1>
        <p>四个核心模块可独立使用，也可沿「定罪研判 → 合规筛查 → 量刑分析」串行。带「开发中」标记的模块尚未接通后端数据。</p>
      </div>
      <label v-if="cases.length" class="case-picker">
        <span>当前案件</span>
        <select :value="currentCaseId ?? ''" @change="pickCase">
          <option v-for="item in cases" :key="item.id" :value="item.id">{{ item.title }}</option>
        </select>
      </label>
      <p v-else-if="caseLoadError" class="notice notice-warning">{{ caseLoadError }}</p>
    </header>
    <section class="home-functions">
      <RouterLink v-for="item in entries" :key="item.key" class="home-feature" :class="{ 'is-dev': item.dev }" :to="item.to">
        <span class="home-feature-icon function-glyph" aria-hidden="true">{{ item.glyph }}</span>
        <h2>{{ item.title }}</h2>
        <p>{{ item.desc }}</p>
        <span v-if="item.dev" class="dev-badge">开发中</span>
        <span v-else class="home-feature-enter">进入 →</span>
      </RouterLink>
    </section>
  </div>
</template>

<style scoped>
.function-glyph {
  display: grid;
  place-items: center;
  color: #fff;
  background: var(--lc-brand-500);
  border-radius: 8px;
  font-size: 18px;
  font-weight: 800;
}
.is-dev h2,
.is-dev p {
  color: var(--lc-muted);
}
.dev-badge {
  margin-top: auto;
  padding-top: 12px;
  color: var(--lc-muted);
  font-size: 12px;
  font-weight: 750;
}
.case-picker {
  display: grid;
  gap: 6px;
  min-width: 220px;
  font-size: 12px;
  font-weight: 650;
}
.case-picker select {
  min-height: 36px;
}
</style>
