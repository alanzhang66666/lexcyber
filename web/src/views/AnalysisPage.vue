<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import CasePhaseBar from '../components/CasePhaseBar.vue'
import PlaceholderBanner from '../components/PlaceholderBanner.vue'
import { findCase, rememberCase } from '../data/placeholder-cases'
import { toastPlaceholder } from '../lib/toast'

const route = useRoute()
const item = computed(() => findCase(String(route.params.caseId)))

onMounted(() => rememberCase(item.value.id))
</script>

<template>
  <div class="page-stack">
    <PlaceholderBanner />
    <header class="page-heading">
      <div>
        <RouterLink class="back-link" :to="`/cases/${item.id}`">← 返回案件工作区</RouterLink>
        <p class="eyebrow">量刑推导链</p>
        <h1>量刑分析</h1>
        <p>{{ item.shortName }} · {{ item.analysis.ruleVersion }} · 示例数据</p>
      </div>
      <div class="heading-actions">
        <CasePhaseBar current="analysis" />
        <RouterLink class="button button-primary" to="/reviews">提交人工复核</RouterLink>
      </div>
    </header>
    <p class="notice notice-warning" role="note">
      <strong>辅助分析，不替代司法裁量</strong>
      <span>罪名、法条版本、调节幅度与建议区间均为界面示例，必须经有权限的专业人员确认后才能进入正式复核。</span>
    </p>
    <section class="analysis-layout">
      <article class="panel reasoning-chain">
        <div class="chain-step">
          <span>1</span>
          <div>
            <small>法定刑档 · 示例</small>
            <h2>{{ item.analysis.statutoryRange }}</h2>
            <button class="text-button" type="button" @click="toastPlaceholder">查看条文与规则版本</button>
          </div>
        </div>
        <div class="chain-step">
          <span>2</span>
          <div>
            <small>基准刑计算 · 示例</small>
            <h2>{{ item.analysis.baseline }}</h2>
            <button class="text-button" type="button" @click="toastPlaceholder">展开计算明细</button>
          </div>
        </div>
        <div class="chain-step">
          <span>3</span>
          <div>
            <small>量刑情节调节</small>
            <div v-for="row in item.analysis.circumstances" :key="row.name" class="circumstance" :class="row.state">
              <b>{{ row.name }}</b>
              <span>{{ row.range }}</span>
              <strong>{{ row.value }}</strong>
              <em>{{ row.state === 'confirmed' ? '已确认' : '待确认' }}</em>
            </div>
          </div>
        </div>
        <div class="chain-step result">
          <span>4</span>
          <div>
            <small>辅助建议区间 · 尚未提交审核</small>
            <h2>{{ item.analysis.interval }}</h2>
            <p>待确认项变化时仅重算未锁定节点。本数字为占位，不作为宣告刑建议。</p>
          </div>
        </div>
      </article>
      <aside class="panel">
        <div class="panel-heading"><div><p class="section-index">BASIS</p><h2>依据与风险</h2></div></div>
        <div class="basis-card">
          <small>规则</small>
          <strong>{{ item.analysis.ruleVersion }}</strong>
          <button class="text-button" type="button" @click="toastPlaceholder">查看规则节点</button>
        </div>
        <div v-if="item.attention" class="basis-card risk">
          <small>风险</small>
          <strong>{{ item.attention }}</strong>
          <RouterLink class="text-button" :to="`/cases/${item.id}/docket`">返回阅卷核验</RouterLink>
        </div>
        <label class="decision-comment">
          <span>审核备注</span>
          <textarea disabled placeholder="填写调节幅度选择理由（占位）" />
        </label>
        <button class="button button-quiet" type="button" @click="toastPlaceholder">比较方案（占位）</button>
      </aside>
    </section>
  </div>
</template>
