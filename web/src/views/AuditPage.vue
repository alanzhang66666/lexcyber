<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
import type { ReviewRecord } from '../api-types'
import { moduleTitle } from '../data/modules'

const rows = ref<ReviewRecord[]>([])
const loading = ref(true)
const error = ref('')

function formatTime(value?: string | null) {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(d)
}

function actionLabel(review: ReviewRecord) {
  if (review.archiveStatus === 'archived') return '归档'
  if (review.status === 'approved') return '批准'
  if (review.status === 'rejected') return '退回'
  return '待复核'
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const page = await api.listReviews({ size: 50 })
    rows.value = page.items
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '审计记录读取失败。'
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
        <p class="eyebrow">统计与审计</p>
        <h1>统计与审计</h1>
        <p>复核留痕来自当前账号属主案件，不编造通过率或耗时。</p>
      </div>
      <RouterLink class="button button-quiet" to="/reviews">打开复核队列</RouterLink>
    </header>
    <section class="metric-grid">
      <article class="metric-card"><span>复核记录</span><strong>{{ loading ? '…' : rows.length }}</strong></article>
      <article class="metric-card"><span>待复核</span><strong>{{ loading ? '…' : rows.filter((r) => r.status === 'pending' && r.archiveStatus !== 'archived').length }}</strong></article>
      <article class="metric-card"><span>已归档</span><strong>{{ loading ? '…' : rows.filter((r) => r.archiveStatus === 'archived').length }}</strong></article>
    </section>
    <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
    <article class="panel">
      <div class="panel-heading"><div><p class="section-index">01</p><h2>审计留痕</h2></div></div>
      <div v-if="loading" class="empty-state">正在读取复核留痕…</div>
      <table v-else-if="rows.length" class="audit-table">
        <thead>
          <tr><th>时间</th><th>对象</th><th>操作</th><th>操作人</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.id">
            <td>{{ formatTime(row.decidedAt) }}</td>
            <td>{{ moduleTitle(row.module) }} · {{ row.caseId || '未关联案件' }}</td>
            <td>{{ actionLabel(row) }}</td>
            <td>{{ row.actor || '—' }}</td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty-state">
        <strong>暂无复核留痕</strong>
        <p>完成定罪或量刑复核后，记录会出现在这里。</p>
      </div>
    </article>
  </div>
</template>
