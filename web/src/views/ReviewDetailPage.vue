<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ApiError, api } from '../api'
import type { ResultPayload, ReviewRecord, TaskView } from '../api-types'
import ResultContent from '../components/ResultContent.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { moduleTitle } from '../data/modules'

const props = defineProps<{ reviewId: string }>()
const review = ref<ReviewRecord | null>(null)
const task = ref<TaskView | null>(null)
const result = ref<ResultPayload | null>(null)
const comment = ref('')
const loading = ref(true)
const deciding = ref<'approve' | 'reject' | ''>('')
const archiving = ref(false)
const error = ref('')
const success = ref('')
const versionConflict = computed(() => Boolean(
  review.value && result.value && review.value.resultVersion !== result.value.version,
))
const canDecide = computed(() => Boolean(
  review.value?.status === 'pending'
  && result.value
  && review.value.resultVersion === result.value.version,
))

async function load() {
  loading.value = true
  error.value = ''
  try {
    review.value = await api.getReview(props.reviewId)
    comment.value = review.value.comment || ''
    if (review.value.taskId) {
      task.value = await api.getTask(review.value.taskId)
      if (task.value.result) result.value = await api.getTaskResult(task.value.id)
    } else if (review.value.caseId) {
      const moduleName = review.value.moduleState
        || (review.value.module === 'compliance' || review.value.module === 'conviction' ? review.value.module : null)
      if (moduleName === 'compliance' || moduleName === 'conviction') {
        const state = await api.getCaseModule(review.value.caseId, moduleName)
        result.value = {
          resultId: review.value.id,
          version: review.value.resultVersion,
          type: 'case.module.content.v1',
          contentHash: '',
          content: state.content,
        }
      }
    }
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '复核记录读取失败。'
  } finally {
    loading.value = false
  }
}

async function decide(decision: 'approve' | 'reject') {
  if (!review.value || !comment.value.trim()) return
  deciding.value = decision
  error.value = ''
  success.value = ''
  try {
    review.value = await api.decideReview(review.value.id, decision, {
      resultVersion: review.value.resultVersion,
      comment: comment.value.trim(),
    })
    success.value = decision === 'approve' ? '已批准当前结果版本。' : '已拒绝当前结果版本。'
  } catch (caught) {
    error.value = caught instanceof ApiError && caught.status === 409
      ? '结果版本或复核状态已经变化。请重新读取后再作决定。'
      : caught instanceof Error ? caught.message : '复核决定提交失败。'
  } finally {
    deciding.value = ''
  }
}

async function archive() {
  if (!review.value) return
  archiving.value = true
  error.value = ''
  success.value = ''
  try {
    review.value = await api.archiveReview(review.value.id)
    success.value = '已归档。该记录保留决定留痕，不再出现在未归档队列中。'
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '归档失败。'
  } finally {
    archiving.value = false
  }
}

onMounted(() => void load())
</script>

<template>
  <div class="page-stack">
    <header class="page-heading compact-heading">
      <div>
        <RouterLink class="back-link" to="/reviews">← 返回复核队列</RouterLink>
        <p class="eyebrow">版本化决定</p>
        <h1>复核结果版本</h1>
        <p class="mono heading-id">{{ reviewId }}</p>
      </div>
      <StatusBadge v-if="review" :status="review.status" />
    </header>
    <p v-if="error" class="notice notice-error" role="alert">
      {{ error }} <button v-if="error.includes('变化')" class="text-button" type="button" @click="load">重新读取</button>
    </p>
    <p v-if="success" class="notice notice-success" role="status">{{ success }}</p>
    <div v-if="loading" class="panel empty-state" aria-live="polite">正在装载复核记录与结果…</div>
    <section v-else-if="review" class="review-workspace">
      <article class="panel evidence-panel">
        <div class="panel-heading">
          <div><p class="section-index">01</p><h2>待核验结果</h2></div>
          <div class="heading-marks">
            <span v-if="review.archiveStatus === 'archived'" class="subtle-chip">已归档</span>
            <span class="subtle-chip mono">v{{ review.resultVersion }}</span>
          </div>
        </div>
        <dl class="data-list inline-data">
          <div><dt>来源模块</dt><dd>{{ moduleTitle(review.module) }}</dd></div>
          <div><dt>案件</dt><dd><RouterLink v-if="review.caseId" class="mono" :to="`/cases/${review.caseId}`">{{ review.caseId }}</RouterLink><span v-else>未关联</span></dd></div>
          <div><dt>任务</dt><dd><RouterLink v-if="review.taskId" class="mono" :to="{ name: 'task-detail', params: { taskId: review.taskId } }">{{ review.taskId }}</RouterLink><span v-else>未关联</span></dd></div>
          <div><dt>执行状态</dt><dd>{{ task?.status || '未知' }}</dd></div>
          <div><dt>结果类型</dt><dd class="mono">{{ result?.type || '—' }}</dd></div>
          <div><dt>内容哈希</dt><dd class="mono">{{ result?.contentHash || '—' }}</dd></div>
        </dl>
        <div v-if="result" class="result-block">
          <ResultContent :content="result.content" />
        </div>
        <div v-else class="empty-state"><strong>没有可显示的结果内容</strong><p>请核对任务状态或稍后重新读取。</p></div>
      </article>
      <aside class="panel decision-panel">
        <div class="panel-heading"><div><p class="section-index">02</p><h2>复核决定</h2></div></div>
        <div class="version-lock">
          <span aria-hidden="true">◇</span>
          <p><strong>版本锁定</strong><small>本次决定仅适用于结果 v{{ review.resultVersion }}；服务端将拒绝旧版本提交。</small></p>
        </div>
        <p v-if="versionConflict" class="notice notice-error" role="alert">当前结果为 v{{ result?.version }}，与待复核的 v{{ review.resultVersion }} 不一致。请返回队列刷新，不要提交决定。</p>
        <p v-else-if="review.status === 'pending' && !result" class="notice notice-error" role="alert">结果内容尚未成功加载，当前不能提交复核决定。</p>
        <div class="checklist">
          <p><strong>审核清单</strong></p>
          <label class="check-row"><input type="checkbox" disabled checked /><span>对照当前结果版本</span></label>
          <label class="check-row"><input type="checkbox" disabled checked /><span>决定写入复核留痕</span></label>
        </div>
        <label class="decision-comment">
          <span>复核意见 <b aria-hidden="true">*</b></span>
          <textarea v-model="comment" rows="8" maxlength="5000" :disabled="!canDecide" required placeholder="写明依据哪段摘要、为何批准或拒绝，以及残留风险" />
          <small>{{ comment.length.toLocaleString() }} / 5,000</small>
        </label>
        <div v-if="canDecide" class="decision-actions decision-actions-three">
          <button class="button button-danger" :disabled="Boolean(deciding) || !comment.trim()" type="button" @click="decide('reject')">
            {{ deciding === 'reject' ? '正在拒绝…' : '拒绝结果' }}
          </button>
          <button class="button button-primary" :disabled="Boolean(deciding) || !comment.trim()" type="button" @click="decide('approve')">
            {{ deciding === 'approve' ? '正在批准…' : '批准结果' }}
          </button>
        </div>
        <div v-else class="notice"><strong>复核已经结束</strong><span>决定：{{ review.decision }}<template v-if="review.actor"> · 操作人：{{ review.actor }}</template></span></div>
        <div v-if="review.status !== 'pending'" class="archive-row">
          <template v-if="review.archiveStatus !== 'archived'">
            <small>归档后将保留决定留痕，并从默认队列视图中收起。</small>
            <button class="button button-quiet" type="button" :disabled="archiving" @click="archive">
              {{ archiving ? '正在归档…' : '归档此复核记录' }}
            </button>
          </template>
          <small v-else>此记录已归档，留痕可在归档视图中查看。</small>
        </div>
      </aside>
    </section>
  </div>
</template>

<style scoped>
.heading-marks {
  display: flex;
  align-items: center;
  gap: 8px;
}
.archive-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--lc-border, #e5e7eb);
}
.archive-row small {
  color: var(--lc-muted, #6b7280);
}
</style>
