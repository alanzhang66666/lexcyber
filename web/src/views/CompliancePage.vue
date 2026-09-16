<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useCaseModule } from '../composables/useCaseModule'
import FactCard from '../components/FactCard.vue'
import { APPLICABILITY_LABEL, toAnalysisFacts } from '../lib/module-content'

const route = useRoute()
const router = useRouter()
const caseId = computed(() => String(route.params.caseId || ''))
const { loading, error, caseItem, moduleState, confirming, confirmError, isPlaceholder, load, confirm } = useCaseModule(caseId, 'compliance')

const facts = computed(() => (moduleState.value ? toAnalysisFacts(moduleState.value.content) : []))
const rawContent = computed(() => (moduleState.value ? JSON.stringify(moduleState.value.content, null, 2) : ''))
const showRaw = ref(false)
const workspaceTo = computed(() => (caseItem.value ? `/cases/${caseItem.value.id}` : '/cases'))

function formatTime(value?: string | null) {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(d)
}

function handleLocate() {
  if (caseItem.value) void router.push(`/cases/${caseItem.value.id}`)
}

onMounted(() => void load())
watch(caseId, () => void load())
</script>

<template>
  <div class="page-stack">
    <header class="page-heading">
      <div>
        <RouterLink class="back-link" :to="workspaceTo">← 返回案件工作区</RouterLink>
        <p class="eyebrow">模块一 · 合规筛查</p>
        <h1>合规筛查</h1>
        <p>{{ caseItem?.title || '未接通案件' }} · 整理合规事实与风险时间线</p>
      </div>
      <div class="heading-actions">
        <span v-if="moduleState" class="subtle-chip">{{ APPLICABILITY_LABEL[moduleState.applicability] }}</span>
        <RouterLink class="button button-primary" to="/reviews">提交人工复核</RouterLink>
      </div>
    </header>

    <p class="notice notice-warning" role="note">
      <strong>辅助分析，不替代专业判断</strong>
      <span>本页只展示模块返回的事实与来源，不在前端计算合规结论或风险分数。C 案用事实清单，A/B 案显示「不适用及原因」。</span>
    </p>

    <div v-if="loading" class="panel empty-state" aria-live="polite">正在读取案件与模块结果…</div>

    <div v-else-if="error" class="panel">
      <p class="notice notice-error" role="alert">{{ error }}</p>
      <button class="button button-quiet" type="button" @click="load">重试</button>
    </div>

    <div v-else-if="isPlaceholder" class="panel empty-state">
      <strong>请先选择真实案件</strong>
      <p>合规筛查挂在具体案件下，示例案件不适用。请到案件中心新建或选择案件。</p>
      <RouterLink class="button button-primary" to="/cases">前往案件中心</RouterLink>
    </div>

    <template v-else>
      <section class="panel">
        <div class="panel-heading"><div><p class="section-index">01</p><h2>模块状态</h2></div></div>
        <template v-if="moduleState">
          <dl class="data-list inline-data">
            <div><dt>适用性</dt><dd>{{ APPLICABILITY_LABEL[moduleState.applicability] }}</dd></div>
            <div><dt>状态</dt><dd>{{ moduleState.status === 'confirmed' ? '已确认' : '草稿' }}</dd></div>
            <div><dt>版本</dt><dd class="mono">v{{ moduleState.version }}</dd></div>
            <div><dt>事实快照</dt><dd>{{ moduleState.factsStale ? '已过期，需重新确认事实' : '最新' }}</dd></div>
            <div><dt>更新时间</dt><dd>{{ formatTime(moduleState.updatedAt) }}</dd></div>
            <div><dt>来源版本</dt><dd class="mono">{{ moduleState.sourceVersion || '—' }}</dd></div>
          </dl>
          <p v-if="moduleState.factsStale" class="notice notice-warning" role="note">
            <strong>事实快照已过期</strong>
            <span>案件事实已变更，请回到案件工作区重新确认事实后再刷新本模块。</span>
          </p>
        </template>
        <div v-else class="empty-state">
          <strong>该模块尚未产生结果</strong>
          <p>完成案件材料上传与事实确认后，由引擎生成合规事实梳理。</p>
        </div>
      </section>

      <section class="panel">
        <div class="panel-heading"><div><p class="section-index">02</p><h2>合规事实梳理</h2></div></div>
        <p class="panel-note">按以下维度整理客观事实，作为行为归属与主观认识的审查底稿。</p>
        <div v-if="facts.length" class="fact-list">
          <FactCard v-for="f in facts" :key="f.id ?? f.statement" :fact="f" @locate="handleLocate" />
        </div>
        <dl v-else class="data-list">
          <div><dt>制度与岗位</dt><dd class="placeholder-text">制度名称/版本、岗位职责与审批要求 —— 待引擎输出</dd></div>
          <div><dt>制度执行</dt><dd class="placeholder-text">培训、审计、业务留痕、是否绕过制度 —— 待引擎输出</dd></div>
          <div><dt>业务审批</dt><dd class="placeholder-text">申请人/审批人/时间/结果 —— 待引擎输出</dd></div>
          <div><dt>风险预警与处置</dt><dd class="placeholder-text">告警/投诉/举报及处置 —— 待引擎输出</dd></div>
          <div><dt>境外关联</dt><dd class="placeholder-text">境外主体、指令、资金流向 —— 待引擎输出</dd></div>
          <div><dt>重大反向风险线索</dt><dd class="placeholder-text">预警未整改、制度执行脱节等 —— 待引擎输出</dd></div>
          <div><dt>正常业务解释</dt><dd class="placeholder-text">真实合同/客户/物流/服务 —— 待引擎输出</dd></div>
        </dl>
      </section>

      <section class="panel">
        <div class="panel-heading"><div><p class="section-index">03</p><h2>合规与风险时间线</h2></div></div>
        <p class="panel-note">按时间顺序排列合规相关事实，标注发生时间、内容、材料来源与整理维度。</p>
        <div class="empty-state">
          <strong>暂无时间线</strong>
          <p>完成合规事实梳理后生成。</p>
        </div>
      </section>

      <section v-if="moduleState" class="panel">
        <div class="panel-heading">
          <div><p class="section-index">04</p><h2>结果内容（原始）</h2></div>
          <button class="text-button" type="button" @click="showRaw = !showRaw">{{ showRaw ? '收起' : '查看' }}</button>
        </div>
        <p class="panel-note">T3 精确 key 尚未会签，暂以原始载荷展示，便于核对字段结构。</p>
        <pre v-if="showRaw" class="raw-payload">{{ rawContent }}</pre>
      </section>

      <div v-if="moduleState" class="action-box">
        <p>{{ moduleState.status === 'confirmed' ? '该模块结果已确认，可提交人工复核。' : '核对事实与来源后确认本模块结果。' }}</p>
        <button
          class="button button-primary"
          type="button"
          :disabled="confirming || moduleState.status === 'confirmed'"
          @click="confirm"
        >
          {{ confirming ? '确认中…' : moduleState.status === 'confirmed' ? '已确认' : '确认模块结果' }}
        </button>
      </div>
      <p v-if="confirmError" class="notice notice-error" role="alert">{{ confirmError }}</p>
    </template>
  </div>
</template>

<style scoped>
.placeholder-text { color: var(--lc-muted); }
.fact-list {
  display: grid;
  gap: 10px;
}
</style>
