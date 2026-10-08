<script setup lang="ts">
import { ref, watch } from 'vue'
import { api } from '../api'
import type { CaseView } from '../api-types'

const props = defineProps<{ caseItem: CaseView }>()
const emit = defineEmits<{ updated: [item: CaseView] }>()
const date = ref('')
const saving = ref(false)
const error = ref('')
let epoch = 0
watch(() => [props.caseItem.id, props.caseItem.asOfDate], () => {
  epoch++
  date.value = props.caseItem.asOfDate ?? ''
  saving.value = false
  error.value = ''
}, { immediate: true })

async function save() {
  if (!date.value || saving.value) return
  const requestEpoch = epoch
  const current = props.caseItem
  saving.value = true
  error.value = ''
  try {
    const updated = await api.updateCaseAnalysisDate(current.id, date.value, current.asOfDate ?? null)
    if (requestEpoch === epoch) emit('updated', updated)
  } catch (caught) {
    if (requestEpoch === epoch) error.value = caught instanceof Error ? caught.message : '日期保存失败。'
  } finally {
    if (requestEpoch === epoch) saving.value = false
  }
}
</script>

<template>
  <article class="panel">
    <h2>法律分析基准日期</h2>
    <p>规则按此日期选择。请根据案件填写；修改后，模块结果和文书需要重新执行与复核，历史版本保留。</p>
    <form class="form-stack" @submit.prevent="save">
      <label><span>基准日期</span><input v-model="date" type="date" required /></label>
      <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
      <button class="button button-primary" :disabled="saving || !date || date === caseItem.asOfDate">
        {{ saving ? '正在保存…' : '保存基准日期' }}
      </button>
    </form>
  </article>
</template>
