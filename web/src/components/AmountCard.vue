<script setup lang="ts">
import { computed } from 'vue'
import type { AmountEntry, AmountKind } from '../api-types'
import LocatorChip from './LocatorChip.vue'
import VerificationBadge from './VerificationBadge.vue'

/**
 * 金额口径卡：标签 + 数值 + 币种 + 证据定位 + 确认状态。
 * 八类口径必须分开展示；账户总流水不得冒充犯罪所得，故单独给出提示。
 */
const props = defineProps<{ amount: AmountEntry }>()
const emit = defineEmits<{ locate: [locator: string] }>()

const KIND_LABELS: Record<AmountKind, string> = {
  account_total_flow: '账户总流水',
  fraud_related_inflow: '涉诈流入',
  payment_settlement: '支付结算',
  crime_amount: '犯罪数额',
  crime_proceeds: '犯罪所得 / 单位获利',
  personal_participation: '个人参与数额',
  personal_profit: '个人获利',
  restitution: '退赔 / 退缴',
  unclassified_amount: '未分类金额',
}

const label = computed(() => props.amount.label || KIND_LABELS[props.amount.kind] || props.amount.kind)
const isTotalFlow = computed(() => props.amount.kind === 'account_total_flow')
const isUnclassified = computed(() => props.amount.kind === 'unclassified_amount')

function formatValue() {
  const v = props.amount.value
  if (v === null || v === undefined) return '—'
  const num = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 }).format(v)
  return `${num}${props.amount.currency ? ' ' + props.amount.currency : ''}`
}
</script>

<template>
  <div class="amount-card">
    <div class="amount-main">
      <span class="amount-kind">{{ label }}</span>
      <span class="amount-value">{{ formatValue() }}</span>
      <VerificationBadge :status="amount.status" />
    </div>
    <p v-if="isTotalFlow" class="amount-hint">账户总流水 ≠ 犯罪所得，仅作流水口径，不得与其他口径互换。</p>
    <p v-else-if="isUnclassified" class="amount-hint">无法判断时保持「待确认」，不得归入已确认口径。</p>
    <div v-if="amount.locator" class="amount-foot">
      <LocatorChip :locator="amount.locator" @locate="(l) => emit('locate', l)" />
    </div>
  </div>
</template>

<style scoped>
.amount-card {
  display: grid;
  gap: 8px;
  padding: 12px 16px;
  background: var(--lc-surface);
  border: 1px solid var(--lc-line);
  border-radius: 8px;
}
.amount-main {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.amount-kind {
  color: var(--lc-brand-900);
  font-size: 13px;
  font-weight: 750;
}
.amount-value {
  color: var(--lc-ink);
  font-size: 13px;
  font-variant-numeric: tabular-nums;
}
.amount-hint {
  margin: 0;
  padding: 6px 10px;
  color: #815000;
  background: var(--lc-review-soft);
  border-left: 3px solid var(--lc-review);
  font-size: 11px;
  line-height: 1.5;
}
.amount-foot {
  display: flex;
}
</style>
