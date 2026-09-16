<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import type { CaseView, SentencingResult } from '../api-types'
import CasePhaseBar from '../components/CasePhaseBar.vue'
import PlaceholderBanner from '../components/PlaceholderBanner.vue'
import SentencingResultPanel from '../components/SentencingResultPanel.vue'
import { isPlaceholderCaseId } from '../data/placeholder-cases'
import { rememberT1Case } from '../lib/current-case'

const route = useRoute()
const router = useRouter()
const caseId = computed(() => String(route.params.caseId || ''))
const loading = ref(true)
const error = ref('')
const caseItem = ref<CaseView | null>(null)
// 等 T1 打开 sentencing.calculate 公开口（501）后，从任务结果归一化填充，本页即渲染真实版式。
const sentencingResult = ref<SentencingResult | null>(null)

const workspaceTo = computed(() => (caseItem.value ? `/cases/${caseItem.value.id}` : '/cases'))

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

function handleLocate() {
  if (caseItem.value) void router.push(`/cases/${caseItem.value.id}`)
}

onMounted(() => {
  void load()
})

watch(caseId, () => {
  void load()
})
</script>

<template>
  <div class="page-stack">
    <PlaceholderBanner />
    <header class="page-heading">
      <div>
        <RouterLink class="back-link" :to="workspaceTo">← 返回案件工作区</RouterLink>
        <p class="eyebrow">量刑推导链</p>
        <h1>量刑分析</h1>
        <p>{{ caseItem?.title || '未接通案件' }} · 量刑接口未接通</p>
      </div>
      <div class="heading-actions">
        <CasePhaseBar current="analysis" />
        <RouterLink class="button button-primary" to="/reviews">提交人工复核</RouterLink>
      </div>
    </header>
    <p class="notice notice-warning" role="note">
      <strong>辅助分析，不替代司法裁量</strong>
      <span>本页不展示示例刑期、法条摘录或调节幅度。未接通前请勿把本页内容当作研判结果。</span>
    </p>
    <div v-if="loading" class="panel empty-state" aria-live="polite">正在读取案件…</div>
    <div v-else-if="error" class="panel">
      <p class="notice notice-error" role="alert">{{ error }}</p>
      <button class="button button-quiet" type="button" @click="load">重试</button>
    </div>
    <section v-else-if="sentencingResult" class="panel">
      <div class="panel-heading"><div><p class="section-index">02</p><h2>量刑计算明细</h2></div></div>
      <SentencingResultPanel :result="sentencingResult" @locate="handleLocate" />
    </section>
    <section v-else class="panel empty-state">
      <strong>量刑结果未接通</strong>
      <p>T2 正式页不再渲染占位案件。量刑计算仍由服务端 501 门控，请到案件工作区处理材料与事实。</p>
      <RouterLink class="button button-primary" :to="workspaceTo">前往案件工作区</RouterLink>
    </section>
  </div>
</template>
