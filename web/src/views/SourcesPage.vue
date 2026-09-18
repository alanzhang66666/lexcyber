<script setup lang="ts">
import { ref } from 'vue'
import { ApiError, api } from '../api'
import type { SourceSearchHit } from '../api-types'
import PlaceholderBanner from '../components/PlaceholderBanner.vue'

const query = ref('')
const asOfDate = ref('')
const topK = ref(5)
const hits = ref<SourceSearchHit[]>([])
const searched = ref(false)
const loading = ref(false)
const error = ref('')

async function search() {
  if (!query.value.trim() || loading.value) return
  loading.value = true
  error.value = ''
  searched.value = true
  try {
    const res = await api.searchSources({
      query: query.value.trim(),
      asOfDate: asOfDate.value || null,
      topK: topK.value,
    })
    hits.value = res.items
  } catch (caught) {
    hits.value = []
    if (caught instanceof ApiError && caught.status === 501) {
      error.value = '法源检索未在服务端启用（501）。请在环境配置中打开 LEGAL_SOURCE_SEARCH_ENABLED。'
    } else if (caught instanceof ApiError && caught.status === 401) {
      error.value = '请先登录后再检索法源。'
    } else {
      error.value = caught instanceof Error ? caught.message : '检索失败。'
    }
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="page-stack">
    <PlaceholderBanner />
    <header class="page-heading">
      <div>
        <p class="eyebrow">法源与类案</p>
        <h1>法源与类案</h1>
        <p>检索范围仅覆盖三案演示已核对的官方法源；超范围查询明确返回空集，不作全库检索。</p>
      </div>
    </header>
    <p class="notice notice-warning" role="note">
      <strong>辅助检索，不构成法律适用结论</strong>
      <span>命中条文的时效与适用性仍需法学负责人确认。</span>
    </p>
    <div class="filter-bar panel">
      <label class="wide-search">
        <span>检索</span>
        <input
          v-model="query"
          placeholder="输入法条、关键词或案例编号"
          @keyup.enter="search"
        />
      </label>
      <label>
        <span>有效日期</span>
        <input v-model="asOfDate" type="date" />
      </label>
      <label>
        <span>条数</span>
        <input v-model.number="topK" type="number" min="1" max="50" />
      </label>
      <button class="button button-primary" type="button" :disabled="loading || !query.trim()" @click="search">
        {{ loading ? '检索中…' : '检索' }}
      </button>
    </div>
    <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
    <div v-if="loading" class="panel empty-state">正在检索…</div>
    <div v-else-if="searched && !hits.length && !error" class="panel empty-state">
      <strong>无命中</strong>
      <p>该查询超出三案已核法源范围，或关键词未命中条文。</p>
    </div>
    <ul v-else-if="hits.length" class="record-list">
      <li v-for="item in hits" :key="item.sourceId + item.locator">
        <div class="record-main">
          <span>{{ item.title || item.sourceId }}</span>
          <small>{{ item.locator }}<template v-if="item.version"> · {{ item.version }}</template><template v-if="item.jurisdiction"> · {{ item.jurisdiction }}</template></small>
          <blockquote v-if="item.quote" class="source-quote">{{ item.quote }}</blockquote>
        </div>
      </li>
    </ul>
    <div v-else class="panel empty-state">
      <strong>输入关键词开始检索</strong>
      <p>仅覆盖三案演示已核对的十条官方法源版本。</p>
    </div>
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
.filter-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 12px;
}
.filter-bar label {
  display: grid;
  gap: 6px;
}
.filter-bar label span {
  color: var(--lc-muted);
  font-size: 12px;
}
.filter-bar input {
  padding: 8px 10px;
  border: 1px solid var(--lc-line);
  border-radius: 8px;
  background: var(--lc-surface);
  color: var(--lc-ink);
  font-size: 14px;
}
.wide-search {
  flex: 1 1 260px;
}
</style>
