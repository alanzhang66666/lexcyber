<script setup lang="ts">
import { computed } from 'vue'
import type { SentencingResult } from '../api-types'
import AmountCard from './AmountCard.vue'
import BlockedNotice from './BlockedNotice.vue'

/**
 * 量刑结果面板：blocked 时只展示阻断项（不展示刑期）；否则展示参数/步骤/区间/金额口径。
 * 纯展示，回跳原文用 @locate 交给父组件。
 */
const props = defineProps<{ result: SentencingResult }>()
const emit = defineEmits<{ locate: [documentId: string | undefined, locator: string] }>()

const blocked = computed(() => props.result.status === 'blocked' || Boolean(props.result.blockers?.length))
const hasDetail = computed(() => Boolean(
  props.result.parameters?.length
  || props.result.steps?.length
  || props.result.interval
  || props.result.amounts?.length,
))
</script>

<template>
  <div class="sentencing-result">
    <div class="sentencing-meta">
      <span v-if="result.ruleVersion" class="subtle-chip mono">规则 {{ result.ruleVersion }}</span>
      <span class="subtle-chip" :class="{ 'chip-blocked': blocked }">{{ blocked ? '待确认（blocked）' : '计算完成' }}</span>
    </div>

    <BlockedNotice v-if="blocked" :blockers="result.blockers!" />

    <section v-if="result.ruleResults?.length" class="sent-section rule-results">
      <h3>逐规则结果</h3>
      <article v-for="(rule, i) in result.ruleResults" :key="`${rule.ruleId}@${rule.ruleVersion}-${i}`" class="rule-result">
        <div class="rule-result-heading">
          <span class="mono">{{ rule.ruleId || '未命名规则' }}<template v-if="rule.ruleVersion">@{{ rule.ruleVersion }}</template></span>
          <span>{{ rule.status || '未知状态' }}</span>
        </div>
        <template v-if="!blocked">
          <p v-if="rule.termMonths !== null && rule.termMonths !== undefined" class="rule-term">规则计算参考值：{{ rule.termMonths }} 个月</p>
          <p v-if="rule.fine" class="rule-term">{{ rule.fine }}</p>
          <ol v-if="rule.steps?.length" class="rule-steps">
            <li v-for="(step, j) in rule.steps" :key="j">
              <span>{{ step.label || '步骤' }}</span>
              <span v-if="step.detail">{{ step.detail }}</span>
              <code v-if="step.value">{{ step.value }}</code>
            </li>
          </ol>
        </template>
        <ul v-if="blocked && rule.blockers?.length" class="rule-blockers">
          <li v-for="(item, j) in rule.blockers" :key="j">{{ item.message || item.code || item.path || '待确认项' }}</li>
        </ul>
      </article>
    </section>

    <template v-if="!blocked">
      <section v-if="result.parameters?.length" class="sent-section">
        <h3>量刑参数</h3>
        <dl class="data-list inline-data">
          <div v-for="(p, i) in result.parameters" :key="i">
            <dt>{{ p.name || '参数' }}</dt>
            <dd>{{ p.value || '—' }}</dd>
          </div>
        </dl>
      </section>

        <section v-if="result.steps?.length && (result.ruleResults?.length || 0) <= 1" class="sent-section">
        <h3>计算步骤</h3>
        <ol class="step-list">
          <li v-for="(s, i) in result.steps" :key="i" class="chain-step">
            <span>{{ i + 1 }}</span>
            <div>
              <h2>{{ s.label || '步骤' }}</h2>
              <p v-if="s.detail" class="step-detail">{{ s.detail }}</p>
              <p v-if="s.value" class="step-value">{{ s.value }}</p>
            </div>
          </li>
        </ol>
      </section>

      <section v-if="result.interval && (result.ruleResults?.length || 0) <= 1" class="sent-section">
        <h3>计算参考区间</h3>
        <div class="result-meta">
          <span>参考区间（待人工核验，非系统预测）</span>
          <code>{{ result.interval }}</code>
        </div>
      </section>

      <section v-if="result.amounts?.length" class="sent-section">
        <h3>金额口径</h3>
        <p class="panel-note">八类口径分开展示，账户总流水不得冒充犯罪所得。</p>
        <div class="amount-list">
          <AmountCard v-for="(a, i) in result.amounts" :key="i" :amount="a" @locate="(l) => emit('locate', undefined, l)" />
        </div>
      </section>
    </template>

    <p v-if="result.missing?.length" class="notice notice-warning" role="note">
      <strong>缺项提示</strong>
      <span>{{ result.missing.join('；') }}</span>
    </p>

    <div v-if="!blocked && !hasDetail" class="empty-state">
      <strong>暂无计算明细</strong>
      <p>量刑结果尚未返回可展示的参数、步骤或区间。</p>
    </div>
  </div>
</template>

<style scoped>
.sentencing-result {
  display: grid;
  gap: 18px;
}
.sentencing-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.chip-blocked {
  color: #8f1736;
  background: var(--lc-risk-soft);
  border-color: var(--lc-risk);
}
.sent-section {
  display: grid;
  gap: 10px;
}
.sent-section h3 {
  margin: 0;
  color: var(--lc-brand-900);
  font-size: 13px;
}
.rule-results {
  gap: 8px;
}
.rule-result {
  display: grid;
  gap: 6px;
  padding: 10px 12px;
  border: 1px solid var(--lc-line);
  border-radius: 8px;
}
.rule-result-heading {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: var(--lc-muted);
  font-size: 12px;
}
.rule-blockers {
  margin: 0;
  padding-left: 18px;
  color: var(--lc-risk);
  font-size: 12px;
}
.rule-term {
  margin: 0;
  color: var(--lc-ink);
  font-size: 13px;
}
.rule-steps {
  display: grid;
  gap: 4px;
  margin: 0;
  padding-left: 20px;
  color: var(--lc-muted);
  font-size: 12px;
}
.rule-steps li {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.rule-steps code {
  color: var(--lc-ink);
}
.step-list {
  margin: 0;
  padding: 0;
  list-style: none;
}
.step-detail {
  margin: 0 0 4px;
  color: var(--lc-ink);
  font-size: 13px;
  line-height: 1.6;
}
.step-value {
  margin: 0;
  color: var(--lc-muted);
  font-size: 12px;
}
.amount-list {
  display: grid;
  gap: 10px;
}
</style>
