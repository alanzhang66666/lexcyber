<script setup lang="ts">
import PlaceholderBanner from '../components/PlaceholderBanner.vue'
import { PLACEHOLDER_RULE_NODES } from '../data/placeholder-cases'
import { toastPlaceholder } from '../lib/toast'
</script>

<template>
  <div class="page-stack">
    <PlaceholderBanner />
    <header class="page-heading">
      <div>
        <p class="eyebrow">量刑规则</p>
        <h1>量刑规则</h1>
        <p>规则版本、节点与调节幅度的工作台预置。未连接规则引擎，禁止将示例幅度当作正式结论。</p>
      </div>
      <span class="subtle-chip">规则 V2026.2 · 示例</span>
    </header>
    <section class="work-grid">
      <article class="panel">
        <div class="panel-heading"><div><p class="section-index">01</p><h2>版本时间线</h2></div></div>
        <ol class="rule-timeline">
          <li><strong>V2026.2</strong><small>当前示例基准 · 2026-09-04</small></li>
          <li><strong>V2025.4</strong><small>历史版本占位</small></li>
        </ol>
      </article>
      <article class="panel">
        <div class="panel-heading"><div><p class="section-index">02</p><h2>规则节点</h2></div></div>
        <ul class="record-list">
          <li v-for="node in PLACEHOLDER_RULE_NODES" :key="node.id">
            <button class="source-row" type="button" @click="toastPlaceholder">
              <div class="record-main">
                <span>{{ node.title }}</span>
                <small>{{ node.detail }}</small>
              </div>
            </button>
          </li>
        </ul>
      </article>
    </section>
  </div>
</template>
