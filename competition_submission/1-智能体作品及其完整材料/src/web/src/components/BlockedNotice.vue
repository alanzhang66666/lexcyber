<script setup lang="ts">
import type { Blocker } from '../api-types'

/**
 * 阻断提示：量刑返回 blocked 时展示 blockers[] 待确认项。
 * 只提示待处理项，不展示空结果，也不把基准刑（benchmark_disposition）当作系统预测。
 */
const props = defineProps<{ blockers: Blocker[] }>()
</script>

<template>
  <section v-if="blockers.length" class="blocked-notice" role="alert">
    <div class="blocked-head">
      <strong>量刑结果待确认（blocked）</strong>
      <span>存在阻断项，暂不展示刑期结果；基准刑仅供参考，不作为系统预测。</span>
    </div>
    <ol class="blocker-list">
      <li v-for="(b, i) in blockers" :key="i">
        <span v-if="b.code" class="blocker-code mono">{{ b.code }}</span>
        <div class="blocker-body">
          <strong>{{ b.message || '待确认项' }}</strong>
          <small v-if="b.path" class="mono">{{ b.path }}</small>
        </div>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.blocked-notice {
  display: grid;
  gap: 12px;
  padding: 16px;
  color: #8f1736;
  background: var(--lc-risk-soft);
  border: 1px solid var(--lc-risk);
  border-left: 4px solid var(--lc-risk);
  border-radius: 8px;
}
.blocked-head {
  display: grid;
  gap: 4px;
}
.blocked-head strong {
  font-size: 14px;
}
.blocked-head span {
  color: #8f1736;
  font-size: 12px;
  line-height: 1.6;
}
.blocker-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 8px;
}
.blocker-list li {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  background: rgb(255 255 255 / 55%);
  border-radius: 6px;
}
.blocker-code {
  flex: 0 0 auto;
  padding: 2px 8px;
  color: #8f1736;
  background: rgb(199 47 85 / 10%);
  border-radius: 4px;
  font-size: 11px;
}
.blocker-body {
  display: grid;
  gap: 3px;
  min-width: 0;
}
.blocker-body strong {
  color: var(--lc-ink);
  font-size: 12px;
  line-height: 1.5;
}
.blocker-body small {
  color: #8f1736;
  font-size: 11px;
  overflow-wrap: anywhere;
}
</style>
