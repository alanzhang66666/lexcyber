<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import CasePhaseBar from '../components/CasePhaseBar.vue'
import PlaceholderBanner from '../components/PlaceholderBanner.vue'
import { PHASE_LABEL, RISK_LABEL, findCase, rememberCase } from '../data/placeholder-cases'

const route = useRoute()
const item = computed(() => findCase(String(route.params.caseId)))

onMounted(() => rememberCase(item.value.id))
watch(() => item.value.id, (id) => rememberCase(id))
</script>

<template>
  <div class="page-stack">
    <PlaceholderBanner />
    <header class="page-heading">
      <div>
        <RouterLink class="back-link" to="/cases">← 返回案件中心</RouterLink>
        <p class="eyebrow">案件工作区</p>
        <h1>{{ item.shortName }}</h1>
        <p>{{ item.caseNumber }} · {{ item.charge }} · {{ item.jurisdiction }}</p>
      </div>
      <div class="heading-aside">
        <span class="aside-label">当前阶段</span>
        <strong>{{ PHASE_LABEL[item.phase] }} · {{ RISK_LABEL[item.risk] }}</strong>
      </div>
    </header>
    <CasePhaseBar :current="item.phase" />
    <section class="detail-grid">
      <article class="panel">
        <div class="panel-heading"><div><p class="section-index">01</p><h2>案情摘要</h2></div></div>
        <p class="lead-copy">{{ item.summary }}</p>
        <dl class="data-list">
          <div><dt>当事人</dt><dd>{{ item.party }}</dd></div>
          <div><dt>审级</dt><dd>{{ item.instance }}</dd></div>
          <div><dt>审核人</dt><dd>{{ item.reviewer }}</dd></div>
          <div><dt>更新</dt><dd>{{ item.updatedAt }}</dd></div>
        </dl>
      </article>
      <article class="panel">
        <div class="panel-heading"><div><p class="section-index">02</p><h2>工作进度</h2></div></div>
        <div class="metric-grid">
          <article class="metric-card"><span>材料</span><strong>{{ item.materialsDone }} / {{ item.materialsTotal }}</strong></article>
          <article class="metric-card"><span>要素确认</span><strong>{{ item.confirmedFields }} / {{ item.totalFields }}</strong></article>
          <article class="metric-card"><span>风险</span><strong>{{ RISK_LABEL[item.risk] }}</strong></article>
        </div>
        <p v-if="item.attention" class="notice">{{ item.attention }}</p>
        <div class="hero-actions">
          <RouterLink class="button button-primary" :to="`/cases/${item.id}/docket`">智能阅卷</RouterLink>
          <RouterLink class="button button-quiet" :to="`/cases/${item.id}/analysis`">量刑分析</RouterLink>
          <RouterLink class="button button-quiet" to="/reviews">人工复核</RouterLink>
          <RouterLink class="button button-quiet" to="/tasks">提交执行任务</RouterLink>
        </div>
      </article>
    </section>
  </div>
</template>
