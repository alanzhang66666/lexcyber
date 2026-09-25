<script setup lang="ts">
import { computed, ref } from 'vue'
import { asStubResult, renderRawContent } from '../lib/result-content'

const props = defineProps<{ content: unknown }>()
const stub = computed(() => asStubResult(props.content))
const assist = computed<Record<string, any> | null>(() => {
  if (!props.content || typeof props.content !== 'object' || Array.isArray(props.content)) return null
  const value = props.content as Record<string, unknown>
  return value.schemaVersion === 'case.assist.v1' ? value as Record<string, any> : null
})
const raw = computed(() => renderRawContent(props.content))
const showRaw = ref(false)
</script>

<template>
  <div v-if="assist" class="result-cards competition-result">
    <div class="notice notice-warning">
      <strong>辅助研判结果，必须人工复核</strong>
      <span>本结果不替代司法裁量。候选路径、风险和缺失信息均需由有权限人员确认。</span>
    </div>
    <dl class="data-list">
      <div><dt>任务状态</dt><dd>{{ assist.status }}</dd></div>
      <div><dt>校核状态</dt><dd>{{ assist.verification?.status || '—' }}</dd></div>
      <div><dt>法源命中</dt><dd>{{ assist.retrieval?.documents?.length || 0 }} 条</dd></div>
      <div><dt>模型</dt><dd class="mono">{{ assist.model?.provider || '—' }} / {{ assist.model?.model || '—' }}</dd></div>
      <div><dt>模型耗时</dt><dd>{{ assist.model?.latencyMs ?? '—' }} ms · {{ assist.model?.attempts ?? 0 }} 次调用</dd></div>
    </dl>
    <section v-if="assist.analysis" class="result-subsection">
      <h3>结构化辅助分析</h3>
      <p>{{ assist.analysis.summary || '未提供摘要' }}</p>
      <ul v-if="assist.analysis.candidate_paths?.length">
        <li v-for="(item, index) in assist.analysis.candidate_paths" :key="index">
          {{ item.label || item.title || item.summary || item }}
        </li>
      </ul>
    </section>
    <section class="result-subsection">
      <h3>法源与校核</h3>
      <ul v-if="assist.retrieval?.documents?.length">
        <li v-for="source in assist.retrieval.documents" :key="source.id">
          {{ source.title }} · {{ source.article }} · {{ source.effective_status }}
        </li>
      </ul>
      <p v-else>没有命中本地法源，任务已阻断。</p>
      <ul v-if="assist.blockers?.length" class="risk-list">
        <li v-for="(blocker, index) in assist.blockers" :key="index">{{ blocker }}</li>
      </ul>
    </section>
    <button class="text-button" type="button" @click="showRaw = !showRaw">
      {{ showRaw ? '收起原始载荷' : '查看原始载荷' }}
    </button>
    <pre v-if="showRaw" class="raw-payload">{{ raw }}</pre>
  </div>
  <div v-else-if="stub" class="result-cards">
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
