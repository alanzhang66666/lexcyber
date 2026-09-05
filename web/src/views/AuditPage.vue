<script setup lang="ts">
import PlaceholderBanner from '../components/PlaceholderBanner.vue'
import { toastPlaceholder } from '../lib/toast'

const rows = [
  { time: '今天 14:32', target: '林某案 · 结果 v3', action: '要素确认', actor: '本地审核员' },
  { time: '今天 10:18', target: '赵某案 · 复核 REV-示-027', action: '提交复核', actor: '本地审核员' },
  { time: '昨天 16:20', target: '陈某案 · 规则 V2026.2', action: '打开分析', actor: '本地审核员' },
]
</script>

<template>
  <div class="page-stack">
    <PlaceholderBanner />
    <header class="page-heading">
      <div>
        <p class="eyebrow">统计与审计</p>
        <h1>统计与审计</h1>
        <p>任务量、复核留痕与阶段耗时。当前图表与表格均为界面占位。</p>
      </div>
      <button class="button button-quiet" type="button" @click="toastPlaceholder">导出审计记录</button>
    </header>
    <section class="metric-grid">
      <article class="metric-card"><span>本周任务</span><strong>18（示例）</strong></article>
      <article class="metric-card"><span>复核通过率</span><strong>— 待接通</strong></article>
      <article class="metric-card"><span>平均阶段耗时</span><strong>— 待接通</strong></article>
    </section>
    <article class="panel">
      <div class="panel-heading"><div><p class="section-index">01</p><h2>审计留痕</h2></div></div>
      <table class="audit-table">
        <thead>
          <tr><th>时间</th><th>对象</th><th>操作</th><th>操作人</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.time + row.target">
            <td>{{ row.time }}</td>
            <td>{{ row.target }}</td>
            <td>{{ row.action }}</td>
            <td>{{ row.actor }}</td>
          </tr>
        </tbody>
      </table>
    </article>
  </div>
</template>
