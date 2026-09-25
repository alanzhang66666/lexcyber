<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ApiError, api } from '../api'
import type { SourceSearchHit } from '../api-types'

const hits = ref<SourceSearchHit[]>([])
const loading = ref(false)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await api.searchSources({ query: '刑法', asOfDate: null, topK: 20 })
    hits.value = res.items
  } catch (caught) {
    hits.value = []
    if (caught instanceof ApiError && caught.status === 501) {
      error.value = '当前演示未开放法源检索。'
    } else {
      error.value = caught instanceof Error ? caught.message : '规则列表读取失败。'
    }
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
        <p class="eyebrow">量刑规则</p>
        <h1>量刑规则</h1>
        <p>三案演示已核法源与规则版本。调节幅度只作为审计说明，不在本页推算刑期。</p>
      </div>
      <span class="subtle-chip">三案已核法源</span>
    </header>
    <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
    <div v-if="loading" class="panel empty-state">正在读取已核法源…</div>
    <section v-else class="panel">
      <div class="panel-heading"><div><p class="section-index">01</p><h2>已核规则与法源</h2></div></div>
      <ul v-if="hits.length" class="record-list">
        <li v-for="item in hits" :key="item.sourceId + item.locator">
          <div class="record-main">
            <span>{{ item.title || item.sourceId }}</span>
            <small>{{ item.locator }}<template v-if="item.version"> · {{ item.version }}</template></small>
            <blockquote v-if="item.quote" class="source-quote">{{ item.quote }}</blockquote>
          </div>
        </li>
      </ul>
      <div v-else class="empty-state">
        <strong>当前没有可展示的法源条目</strong>
        <p>可到「法源与类案」按关键词检索。</p>
        <RouterLink class="button button-primary" to="/sources">前往法源检索</RouterLink>
      </div>
    </section>
  </div>
</template>

<style scoped>
.source-quote {
  margin: 8px 0 0;
  padding: 8px 12px;
  border-left: 3px solid var(--lc-line);
  color: var(--lc-muted);
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
}
</style>
