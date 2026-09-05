<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import CasePhaseBar from '../components/CasePhaseBar.vue'
import PlaceholderBanner from '../components/PlaceholderBanner.vue'
import { findCase, rememberCase, type PlaceholderField } from '../data/placeholder-cases'
import { toastPlaceholder } from '../lib/toast'

const route = useRoute()
const router = useRouter()
const item = computed(() => findCase(String(route.params.caseId)))
const activeDoc = ref(item.value.documents[0]?.id)
const tab = ref<PlaceholderField['tab']>('elements')
const tabs: { id: PlaceholderField['tab']; label: string }[] = [
  { id: 'elements', label: '要素' },
  { id: 'evidence', label: '证据' },
  { id: 'sources', label: '法源' },
  { id: 'issues', label: '待处理' },
]

const currentDoc = computed(() => item.value.documents.find((doc) => doc.id === activeDoc.value) ?? item.value.documents[0])
const fields = computed(() => item.value.fields.filter((field) => field.tab === tab.value))
const groups = computed(() => [...new Set(item.value.documents.map((doc) => doc.group))])

onMounted(() => {
  rememberCase(item.value.id)
  activeDoc.value = item.value.documents[0]?.id
})

watch(() => item.value.id, (id) => {
  rememberCase(id)
  activeDoc.value = item.value.documents[0]?.id
  tab.value = 'elements'
})

const fieldState: Record<PlaceholderField['state'], string> = {
  confirmed: '已确认',
  pending: '待确认',
  conflict: '存在冲突',
}
</script>

<template>
  <div class="page-stack workbench-stack">
    <PlaceholderBanner />
    <header class="workbench-header">
      <div>
        <p class="breadcrumb">案件中心 / {{ item.shortName }}</p>
        <h1>智能阅卷</h1>
      </div>
      <CasePhaseBar current="docket" />
      <RouterLink class="button button-primary" :to="`/cases/${item.id}/analysis`">进入量刑分析</RouterLink>
    </header>
    <section class="workbench">
      <aside class="panel document-tree">
        <div class="panel-heading">
          <div><p class="section-index">FILES</p><h2>卷宗材料</h2></div>
          <button class="button button-quiet" type="button" @click="toastPlaceholder">上传</button>
        </div>
        <template v-for="group in groups" :key="group">
          <p class="tree-label">{{ group }}</p>
          <button
            v-for="doc in item.documents.filter((entry) => entry.group === group)"
            :key="doc.id"
            class="file-item"
            :class="{ active: doc.id === currentDoc?.id, warning: doc.status === 'ocr' }"
            type="button"
            @click="activeDoc = doc.id"
          >
            <b>{{ doc.name }}<small>{{ doc.pages }} 页 · {{ doc.status === 'ocr' ? 'OCR 待校对' : '已解析' }}</small></b>
          </button>
        </template>
      </aside>
      <article class="panel document-viewer">
        <header>
          <strong>{{ currentDoc?.name }}</strong>
          <small>提取文本 · 示例占位</small>
        </header>
        <div class="paper">
          <p>{{ currentDoc?.excerpt || item.summary }}</p>
          <p v-for="field in item.fields.slice(0, 3)" :key="field.id">
            <mark :class="`mark-${field.state}`">{{ field.value }}</mark>
            <small> {{ field.locator }}</small>
          </p>
        </div>
      </article>
      <aside class="panel extraction-panel">
        <div class="panel-heading">
          <div><p class="section-index">TRACE</p><h2>识别结果</h2></div>
        </div>
        <div class="result-tabs">
          <button
            v-for="entry in tabs"
            :key="entry.id"
            :class="{ 'is-active': tab === entry.id }"
            type="button"
            @click="tab = entry.id"
          >
            {{ entry.label }}
          </button>
        </div>
        <article v-for="field in fields" :key="field.id" class="result-card" :class="field.state">
          <small>{{ field.label }}<template v-if="field.confidence"> · {{ field.confidence }}%</template></small>
          <strong>{{ field.value }}</strong>
          <p v-if="field.note">{{ field.note }}</p>
          <footer>
            <button class="text-button" type="button" @click="toastPlaceholder">{{ field.locator }}</button>
            <em>{{ fieldState[field.state] }}</em>
          </footer>
        </article>
        <p v-if="!fields.length" class="panel-note">该分类暂无占位字段。</p>
        <button class="button button-primary" type="button" @click="router.push(`/cases/${item.id}/analysis`)">
          保存并进入量刑分析
        </button>
      </aside>
    </section>
  </div>
</template>
