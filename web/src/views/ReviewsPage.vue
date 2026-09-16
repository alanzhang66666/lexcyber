<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
import type { ReviewRecord } from '../api-types'
import StatusBadge from '../components/StatusBadge.vue'
import { moduleTitle } from '../data/modules'

const reviews = ref<ReviewRecord[]>([])
const loading = ref(true)
const error = ref('')
const statusFilter = ref<'pending' | 'approved' | 'rejected' | 'all'>('pending')

const FILTERS: { value: 'pending' | 'approved' | 'rejected' | 'all'; label: string }[] = [
  { value: 'pending', label: '待复核' },
  { value: 'approved', label: '已批准' },
  { value: 'rejected', label: '已拒绝' },
  { value: 'all', label: '全部' },
]

function versionLabel(review: ReviewRecord) {
  const parts = [`结果 v${review.resultVersion}`]
  if (review.moduleVersion != null) parts.push(`模块 v${review.moduleVersion}`)
  if (review.draftVersion != null) parts.push(`草稿 v${review.draftVersion}`)
  return parts.join(' · ')
}

async function loadReviews() {
  loading.value = true
  error.value = ''
  try {
    const page = await api.listReviews({
      status: statusFilter.value === 'all' ? undefined : statusFilter.value,
      size: 100,
    })
    reviews.value = page.items
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '复核队列读取失败。'
  } finally {
    loading.value = false
  }
}

function selectFilter(value: 'pending' | 'approved' | 'rejected' | 'all') {
  statusFilter.value = value
  void loadReviews()
}

onMounted(() => void loadReviews())
</script>

<template>
  <div class="page-stack">
    <header class="page-heading">
      <div>
        <p class="eyebrow">人工复核</p>
        <h1>人工复核</h1>
        <p>只对当前不可变结果版本作出决定，并留下可审计的复核意见。决定只作用于已接通的引擎结果。</p>
      </div>
      <div class="heading-aside">
        <span class="aside-label">当前队列</span>
        <strong>{{ loading ? '读取中' : `${reviews.length} 项` }}</strong>
      </div>
    </header>

    <section class="panel">
      <div class="panel-heading">
        <div><p class="section-index">01</p><h2>复核队列</h2></div>
        <button class="button button-quiet" :disabled="loading" type="button" @click="loadReviews">刷新队列</button>
      </div>

      <div class="segmented" role="tablist" aria-label="按状态筛选">
        <button
          v-for="f in FILTERS"
          :key="f.value"
          type="button"
          :class="{ 'is-active': statusFilter === f.value }"
          @click="selectFilter(f.value)"
        >
          {{ f.label }}
        </button>
      </div>

      <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
      <div v-if="loading" class="empty-state" aria-live="polite">正在读取复核队列…</div>
      <div v-else-if="!reviews.length" class="empty-state">
        <span aria-hidden="true">✓</span>
        <strong>队列为空</strong>
        <p>{{ statusFilter === 'pending' ? '当前没有待人工决定的结果版本。' : '该筛选下没有复核记录。' }}</p>
      </div>
      <ul v-else class="record-list review-list">
        <li v-for="review in reviews" :key="review.id">
          <RouterLink :to="{ name: 'review-detail', params: { reviewId: review.id } }">
            <div class="record-main">
              <span>{{ moduleTitle(review.module) }} · {{ versionLabel(review) }}</span>
              <small>案件 {{ review.caseId || '未关联' }} · {{ review.id }}</small>
            </div>
            <div class="review-marks">
              <span v-if="review.archiveStatus === 'archived'" class="subtle-chip chip-archived">已归档</span>
              <StatusBadge :status="review.status" />
            </div>
          </RouterLink>
        </li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.review-marks {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 0 0 auto;
}
.chip-archived {
  color: var(--lc-muted);
  border-color: var(--lc-line);
}
</style>
