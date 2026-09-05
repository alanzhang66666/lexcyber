<script setup lang="ts">
import PlaceholderBanner from '../components/PlaceholderBanner.vue'
import { PLACEHOLDER_SOURCES } from '../data/placeholder-cases'
import { toastPlaceholder } from '../lib/toast'
</script>

<template>
  <div class="page-stack">
    <PlaceholderBanner />
    <header class="page-heading">
      <div>
        <p class="eyebrow">法源与类案</p>
        <h1>法源与类案</h1>
        <p>检索法律、司法解释与类案。当前列表为跨境网域犯罪场景的界面示例。</p>
      </div>
    </header>
    <div class="filter-bar panel">
      <label class="wide-search">
        <span>检索</span>
        <input disabled placeholder="输入法条、关键词或案例编号（占位）" />
      </label>
      <button class="button button-quiet" type="button" @click="toastPlaceholder">筛选效力 / 法域</button>
    </div>
    <ul class="record-list">
      <li v-for="item in PLACEHOLDER_SOURCES" :key="item.id">
        <button class="source-row" type="button" @click="toastPlaceholder">
          <div class="record-main">
            <span>{{ item.title }}</span>
            <small>{{ item.kind }} · {{ item.locator }} · {{ item.version }}</small>
          </div>
        </button>
      </li>
    </ul>
  </div>
</template>
