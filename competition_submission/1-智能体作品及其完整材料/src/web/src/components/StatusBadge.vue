<script setup lang="ts">
import { computed } from 'vue'
import type { ReviewStatus, TaskStatus } from '../api-types'

const props = defineProps<{ status: TaskStatus | ReviewStatus }>()
const labels: Record<TaskStatus | ReviewStatus, string> = {
  queued: '排队中', running: '执行中', completed: '已完成', waiting_review: '待人工复核',
  failed: '执行失败', timed_out: '执行超时', rejected: '已拒绝', pending: '待复核',
  approved: '已批准', superseded: '已被新版本替代',
}
const symbol = computed(() => {
  if (['completed', 'approved'].includes(props.status)) return '✓'
  if (['failed', 'timed_out', 'rejected'].includes(props.status)) return '!'
  if (['waiting_review', 'pending', 'superseded'].includes(props.status)) return '◆'
  return '●'
})
</script>

<template>
  <span class="status-badge" :class="`status-${status}`">
    <span aria-hidden="true">{{ symbol }}</span>{{ labels[status] }}
  </span>
</template>
