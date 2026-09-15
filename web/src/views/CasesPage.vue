<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
import type { CaseView } from '../api-types'

const loading = ref(true)
const error = ref('')
const cases = ref<CaseView[]>([])

async function load() {
  loading.value = true
  error.value = ''
  try {
    const page = await api.listCases({ page: 0, size: 50 })
    cases.value = page.items
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '案件列表读取失败。'
  } finally {
    loading.value = false
  }
}

onMounted(() => void load())
</script>

<template>
  <div class="page-stack">
    <header class="page-heading">
      <div>
        <p class="eyebrow">案件中心</p>
        <h1>案件中心</h1>
        <p>统一查看案件、材料与解析状态。列表数据来自服务端。</p>
      </div>
      <RouterLink class="button button-primary" to="/cases/new">新建案件</RouterLink>
    </header>

    <div v-if="loading" class="panel empty-state" aria-live="polite">正在读取案件列表…</div>

    <div v-else-if="error" class="panel">
      <p class="notice notice-error" role="alert">{{ error }}</p>
      <button class="button button-quiet" type="button" @click="load">重试</button>
    </div>

    <div v-else-if="!cases.length" class="panel empty-state">
      <span aria-hidden="true">＋</span>
      <strong>还没有案件</strong>
      <p>新建一个案件后，可在此上传材料并发起解析。</p>
      <RouterLink class="button button-primary" to="/cases/new">新建案件</RouterLink>
    </div>

    <div v-else class="case-card-grid">
      <RouterLink v-for="item in cases" :key="item.id" class="matter-card" :to="`/cases/${item.id}`">
        <div class="matter-top">
          <span class="case-avatar">{{ (item.title || '案').slice(0, 1) }}</span>
          <span class="risk-pill">{{ item.jurisdiction || '未填法域' }}</span>
        </div>
        <h2>{{ item.title }}</h2>
        <p>{{ item.asOfDate || '未填日期' }}</p>
        <footer>
          <span>{{ item.createdAt }}</span>
        </footer>
      </RouterLink>
      <RouterLink class="matter-card matter-card-new" to="/cases/new">
        <span>+</span>
        <strong>新建案件</strong>
        <small>创建案件并上传卷宗材料</small>
      </RouterLink>
    </div>
  </div>
</template>
