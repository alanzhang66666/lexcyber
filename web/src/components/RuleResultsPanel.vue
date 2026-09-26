<script setup lang="ts">
import type { V2ModuleAnalysis } from '../lib/module-content-v2'

defineProps<{ analysis: V2ModuleAnalysis }>()

const STATUS_LABEL: Record<string, string> = {
  calculated: '已计算',
  blocked: '已阻断',
  not_applicable: '不适用',
}

function statusLabel(s: string): string {
  return STATUS_LABEL[s] ?? s
}

function traceValue(v: unknown): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}
</script>

<template>
  <div class="rule-results">
    <dl class="data-list inline-data">
      <div><dt>执行状态</dt><dd>{{ statusLabel(analysis.status) }}</dd></div>
      <div><dt>规则数</dt><dd class="mono">{{ analysis.rules.length }}</dd></div>
      <div><dt>命中</dt><dd class="mono">{{ analysis.rules.filter((r) => r.fired).length }}</dd></div>
      <div><dt>生成时间</dt><dd class="mono">{{ analysis.generatedAt || '—' }}</dd></div>
    </dl>

    <p v-if="analysis.humanReviewRequired" class="notice notice-info" role="note">
      规则执行结果须人工复核；以下为 approved 规则包对确认事实快照的逐条求值留痕。
    </p>

    <div v-if="analysis.blockers.length" class="blocker-list">
      <p v-for="(b, i) in analysis.blockers" :key="i" class="notice notice-warning" role="note">
        <strong>{{ b.code || '阻断' }}</strong>
        <span class="mono">{{ b.path }}</span> {{ b.message }}
      </p>
    </div>

    <div v-if="analysis.divergence.length" class="blocker-list">
      <p v-for="(d, i) in analysis.divergence" :key="i" class="notice notice-warning" role="note">
        <strong>法源时点分歧</strong>
        <span class="mono">{{ JSON.stringify(d) }}</span>
      </p>
    </div>

    <ul class="rule-list">
      <li v-for="rule in analysis.rules" :key="`${rule.ruleId}@${rule.ruleVersion}`" class="rule-item">
        <div class="rule-head">
          <span class="rule-id mono">{{ rule.ruleId }}@{{ rule.ruleVersion }}</span>
          <span v-if="rule.family" class="subtle-chip">{{ rule.family }}</span>
          <span class="subtle-chip" :class="rule.fired ? 'chip-fired' : 'chip-idle'">
            {{ rule.fired ? '命中' : '未命中' }}
          </span>
        </div>
        <p v-if="rule.outcomeSummary" class="rule-outcome">{{ rule.outcomeSummary }}</p>
        <p v-if="rule.sourceIds.length" class="rule-sources mono">法源：{{ rule.sourceIds.join('、') }}</p>
        <details v-if="rule.trace.length" class="rule-trace">
          <summary>逐条件留痕（{{ rule.trace.length }} 条）</summary>
          <table>
            <thead>
              <tr><th>路径</th><th>算子</th><th>期望</th><th>实际</th><th>结果</th></tr>
            </thead>
            <tbody>
              <tr v-for="(t, i) in rule.trace" :key="i">
                <td class="mono">{{ t.path }}</td>
                <td class="mono">{{ t.op }}</td>
                <td class="mono">{{ traceValue(t.expected) }}</td>
                <td class="mono">{{ t.found === false ? '（缺失）' : traceValue(t.actual) }}</td>
                <td class="mono">{{ t.result === undefined ? '—' : t.result }}</td>
              </tr>
            </tbody>
          </table>
        </details>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.rule-results {
  display: grid;
  gap: 12px;
}
.blocker-list {
  display: grid;
  gap: 8px;
}
.rule-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 10px;
}
.rule-item {
  padding: 12px 14px;
  background: var(--lc-surface);
  border: 1px solid var(--lc-line);
  border-radius: 8px;
  display: grid;
  gap: 8px;
}
.rule-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.rule-id {
  font-size: 13px;
  font-weight: 600;
}
.chip-fired {
  color: var(--lc-brand-800);
  background: var(--lc-brand-100);
}
.chip-idle {
  color: var(--lc-muted);
}
.rule-outcome {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
}
.rule-sources {
  margin: 0;
  color: var(--lc-muted);
  font-size: 12px;
}
.rule-trace summary {
  cursor: pointer;
  color: var(--lc-muted);
  font-size: 12px;
}
.rule-trace table {
  margin-top: 8px;
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.rule-trace th,
.rule-trace td {
  padding: 4px 8px;
  border-bottom: 1px solid var(--lc-line);
  text-align: left;
  vertical-align: top;
}
</style>
