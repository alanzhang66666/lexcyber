<script setup lang="ts">
import { computed, ref } from 'vue'
import { asStubResult, renderRawContent } from '../lib/result-content'

const props = defineProps<{ content: unknown }>()
const stub = computed(() => asStubResult(props.content))
const raw = computed(() => renderRawContent(props.content))
const showRaw = ref(false)
</script>

<template>
  <div v-if="stub" class="result-cards">
    <dl class="data-list">
      <div v-if="stub.summary"><dt>摘要</dt><dd>{{ stub.summary }}</dd></div>
      <div v-if="stub.status"><dt>执行状态</dt><dd>{{ stub.status }}</dd></div>
      <div v-if="stub.review_status"><dt>复核状态</dt><dd>{{ stub.review_status }}</dd></div>
      <div>
        <dt>是否需复核</dt>
        <dd>{{ stub.human_approval_required ? '是' : '否' }}</dd>
      </div>
      <div v-if="stub.runner"><dt>运行器</dt><dd class="mono">{{ stub.runner }}</dd></div>
    </dl>
    <button class="text-button" type="button" @click="showRaw = !showRaw">
      {{ showRaw ? '收起原始载荷' : '查看原始载荷' }}
    </button>
    <pre v-if="showRaw" class="raw-payload">{{ raw }}</pre>
  </div>
  <pre v-else-if="raw">{{ raw }}</pre>
</template>
