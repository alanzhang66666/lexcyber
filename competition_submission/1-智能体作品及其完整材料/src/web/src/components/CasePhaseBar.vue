<script setup lang="ts">
import { computed } from 'vue'
import type { CasePhase } from '../data/placeholder-cases'

const props = defineProps<{ current: CasePhase }>()

const steps: { id: CasePhase; label: string }[] = [
  { id: 'materials', label: '材料' },
  { id: 'docket', label: '要素校对' },
  { id: 'analysis', label: '量刑分析' },
  { id: 'review', label: '审核' },
]

const order: CasePhase[] = ['materials', 'docket', 'analysis', 'review']
const currentIndex = computed(() => Math.max(order.indexOf(props.current), 0))
</script>

<template>
  <ol class="phase-steps" aria-label="案件阶段">
    <li
      v-for="(step, index) in steps"
      :key="step.id"
      :class="{ done: index < currentIndex, current: index === currentIndex }"
    >
      <span>{{ index < currentIndex ? '✓' : index + 1 }}</span>
      {{ step.label }}
    </li>
  </ol>
</template>
