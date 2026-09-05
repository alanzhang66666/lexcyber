<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
import type { ReviewRecord } from '../api-types'
import StatusBadge from '../components/StatusBadge.vue'

const reviews = ref<ReviewRecord[]>([])
const loading = ref(true)
const error = ref('')

async function loadReviews() {
  loading.value = true
  error.value = ''
  try {
    const page = await api.listReviews({ status: 'pending', size: 100 })
    reviews.value = page.items
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '复核队列读取失败。'
  } finally {
    loading.value = false
  }
}

onMounted(() => void loadReviews())
</script>

<template>
  <div class="page-stack">
    <header class="page-heading">
      <div><p class="eyebrow">HUMAN REVIEW</p><h1>人工复核</h1><p>只对当前不可变结果版本作出决定，并留下可审计的复核意见。</p></div>
      <div class="heading-aside"><span class="aside-label">当前队列</span><strong>{{ reviews.length }} 项待处理</strong></div>
    </header>
    <section class="panel">
      <div class="panel-heading">
        <div><p class="section-index">01</p><h2>待复核队列</h2></div>
        <button class="button button-quiet" :disabled="loading" type="button" @click="loadReviews">刷新队列</button>
      </div>
      <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
      <div v-if="loading" class="empty-state" aria-live="polite">正在读取复核队列…</div>
      <div v-else-if="!reviews.length" class="empty-state"><span aria-hidden="true">✓</span><strong>队列已清空</strong><p>当前没有待人工决定的结果版本。</p></div>
      <ul v-else class="record-list review-list">
        <li v-for="review in reviews" :key="review.id">
          <RouterLink :to="{ name: 'review-detail', params: { reviewId: review.id } }">
            <div class="record-main">
              <span class="mono">{{ review.id }}</span>
              <small>任务 {{ review.taskId || '未关联' }} · 结果版本 v{{ review.resultVersion }}</small>
            </div>
            <StatusBadge :status="review.status" />
          </RouterLink>
        </li>
      </ul>
    </section>
  </div>
</template>
