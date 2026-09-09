<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import type { CaseView } from '../api-types'
import CasePhaseBar from '../components/CasePhaseBar.vue'
import PlaceholderBanner from '../components/PlaceholderBanner.vue'
import { isPlaceholderCaseId } from '../data/placeholder-cases'
import { rememberT1Case } from '../lib/current-case'

const route = useRoute()
const caseId = computed(() => String(route.params.caseId || ''))
const loading = ref(true)
const error = ref('')
const caseItem = ref<CaseView | null>(null)

const workspaceTo = computed(() => (caseItem.value ? `/cases/${caseItem.value.id}` : '/cases'))
const analysisTo = computed(() => (caseItem.value ? `/cases/${caseItem.value.id}/analysis` : '/cases'))

async function load() {
  loading.value = true
  error.value = ''
  caseItem.value = null
  if (!caseId.value || isPlaceholderCaseId(caseId.value)) {
    loading.value = false
    return
  }
  try {
    caseItem.value = await api.getCase(caseId.value)
    rememberT1Case(caseItem.value.id)
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '案件读取失败。'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void load()
})

watch(caseId, () => {
  void load()
})
</script>

<template>
  <div class="page-stack workbench-stack">
    <PlaceholderBanner />
    <header class="workbench-header">
      <div>
        <p class="breadcrumb">案件中心 / {{ caseItem?.title || '未接通案件' }}</p>
        <h1>智能阅卷</h1>
      </div>
      <CasePhaseBar current="docket" />
      <RouterLink class="button button-primary" :to="analysisTo">进入量刑分析</RouterLink>
    </header>
    <div v-if="loading" class="panel empty-state" aria-live="polite">正在读取案件…</div>
    <div v-else-if="error" class="panel">
      <p class="notice notice-error" role="alert">{{ error }}</p>
      <button class="button button-quiet" type="button" @click="load">重试</button>
    </div>
    <section v-else class="panel empty-state">
      <strong>阅卷结果未接通</strong>
      <p>本页不展示示例摘录或占位要素。请到案件工作区查看上传、解析正文与事实确认。</p>
      <RouterLink class="button button-primary" :to="workspaceTo">前往案件工作区</RouterLink>
    </section>
  </div>
</template>
