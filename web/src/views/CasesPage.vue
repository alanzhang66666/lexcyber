<script setup lang="ts">
import PlaceholderBanner from '../components/PlaceholderBanner.vue'
import { PHASE_LABEL, PLACEHOLDER_CASES, RISK_LABEL, rememberCase } from '../data/placeholder-cases'
</script>

<template>
  <div class="page-stack">
    <PlaceholderBanner />
    <header class="page-heading">
      <div>
        <p class="eyebrow">案件中心</p>
        <h1>案件中心</h1>
        <p>统一查看跨境网域犯罪案件的材料、分析和审核状态。下列案件为界面示例。</p>
      </div>
      <RouterLink class="button button-primary" to="/cases/new">新建案件</RouterLink>
    </header>
    <div class="filter-bar panel">
      <label class="wide-search">
        <span>搜索</span>
        <input disabled placeholder="搜索案号、案件名称或当事人（占位）" />
      </label>
      <span class="subtle-chip">状态 · 罪名 · 风险 筛选尚未接通</span>
    </div>
    <div class="case-card-grid">
      <RouterLink
        v-for="item in PLACEHOLDER_CASES"
        :key="item.id"
        class="matter-card"
        :to="`/cases/${item.id}`"
        @click="rememberCase(item.id)"
      >
        <div class="matter-top">
          <span class="case-avatar">{{ item.party.slice(0, 1) }}</span>
          <span class="risk-pill" :class="`risk-${item.risk}`">{{ RISK_LABEL[item.risk] }}</span>
        </div>
        <h2>{{ item.shortName }}</h2>
        <p>{{ item.caseNumber }}</p>
        <div class="matter-meta">
          <span>{{ item.instance }}</span>
          <span>{{ item.jurisdiction }}</span>
          <span>{{ item.charge }}</span>
        </div>
        <div class="matter-progress">
          <span>要素确认 {{ item.confirmedFields }} / {{ item.totalFields }}</span>
          <i><em :style="{ width: `${Math.round((item.confirmedFields / item.totalFields) * 100)}%` }" /></i>
        </div>
        <footer>
          <span class="stage-pill">{{ PHASE_LABEL[item.phase] }}</span>
          <time>{{ item.updatedAt }}</time>
        </footer>
      </RouterLink>
      <RouterLink class="matter-card matter-card-new" to="/cases/new">
        <span>+</span>
        <strong>新建案件</strong>
        <small>从卷宗导入或手动创建（占位向导）</small>
      </RouterLink>
    </div>
  </div>
</template>
