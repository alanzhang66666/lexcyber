<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
import type { ReviewRecord } from '../api-types'
import StatusBadge from '../components/StatusBadge.vue'
import { PLACEHOLDER_CASES } from '../data/placeholder-cases'

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
      <div>
        <p class="eyebrow">人工复核</p>
        <h1>人工复核</h1>
        <p>只对当前不可变结果版本作出决定，并留下可审计的复核意见。决定只作用于已接通的引擎结果。</p>
      </div>
      <div class="heading-aside">
        <span class="aside-label">当前队列</span>
        <strong>{{ loading ? '读取中' : `${reviews.length} 项待处理` }}</strong>
      </div>
    </header>
    <section class="panel">
      <div class="panel-heading">
        <div><p class="section-index">01</p><h2>待复核队列</h2></div>
        <button class="button button-quiet" :disabled="loading" type="button" @click="loadReviews">刷新队列</button>
      </div>
      <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
      <div v-if="loading" class="empty-state" aria-live="polite">正在读取复核队列…</div>
      <div v-else-if="!reviews.length" class="empty-state">
        <span aria-hidden="true">✓</span>
        <strong>队列已清空</strong>
        <p>当前没有待人工决定的结果版本。可从「执行任务」提交一条勾选复核的请求。</p>
      </div>
      <ul v-else class="record-list review-list">
        <li v-for="review in reviews" :key="review.id">
          <RouterLink :to="{ name: 'review-detail', params: { reviewId: review.id } }">
            <div class="record-main">
              <span>结果版本 v{{ review.resultVersion }}</span>
              <small>任务 {{ review.taskId || '未关联' }} · {{ review.id }}</small>
            </div>
            <StatusBadge :status="review.status" />
          </RouterLink>
        </li>
      </ul>
    </section>
    <section v-if="!loading && !reviews.length" class="panel">
      <div class="panel-heading">
        <div><p class="section-index">02</p><h2>示例队列（占位）</h2></div>
        <span class="subtle-chip">不写入复核接口</span>
      </div>
      <p class="panel-note">用于预览审核中心信息架构。点击进入对应案件工作区，不会提交决定。</p>
      <ul class="record-list">
        <li v-for="item in PLACEHOLDER_CASES.filter((entry) => entry.phase === 'review' || entry.risk === 'high')" :key="item.id">
          <RouterLink :to="`/cases/${item.id}`">
            <div class="record-main">
              <span>{{ item.shortName }}</span>
              <small>{{ item.attention || item.charge }} · {{ item.updatedAt }}</small>
            </div>
            <span class="risk-pill" :class="`risk-${item.risk}`">{{ item.risk === 'high' ? '高风险' : '中风险' }}</span>
          </RouterLink>
        </li>
      </ul>
    </section>
  </div>
</template>
