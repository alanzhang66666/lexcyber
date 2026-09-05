<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import PlaceholderBanner from '../components/PlaceholderBanner.vue'
import { toastPlaceholder } from '../lib/toast'

const router = useRouter()
const step = ref(1)
const name = ref('')
const caseNumber = ref('')
const charge = ref('涉嫌帮助信息网络犯罪活动')
const jurisdiction = ref('上海市')
const party = ref('')

const canNext = computed(() => step.value > 1 || Boolean(name.value.trim() && party.value.trim()))

function next() {
  if (step.value < 4) step.value += 1
  else {
    toastPlaceholder()
    void router.push('/cases')
  }
}
</script>

<template>
  <div class="page-stack narrow-stack">
    <PlaceholderBanner />
    <header class="page-heading">
      <div>
        <RouterLink class="back-link" to="/cases">← 返回案件中心</RouterLink>
        <p class="eyebrow">新建案件</p>
        <h1>新建案件</h1>
        <p>四步向导用于预置工作流。当前不会写入后端案件库。</p>
      </div>
      <span class="subtle-chip">步骤 {{ step }} / 4</span>
    </header>
    <article class="panel">
      <ol class="wizard-steps">
        <li :class="{ current: step === 1, done: step > 1 }">基本信息</li>
        <li :class="{ current: step === 2, done: step > 2 }">导入卷宗</li>
        <li :class="{ current: step === 3, done: step > 3 }">关联任务</li>
        <li :class="{ current: step === 4 }">确认创建</li>
      </ol>

      <form v-if="step === 1" class="form-stack" @submit.prevent="next">
        <label><span>案件名称 <b>*</b></span><input v-model="name" required placeholder="例如：林某涉嫌跨境电信网络诈骗" /></label>
        <label><span>当事人 <b>*</b></span><input v-model="party" required placeholder="例如：林某" /></label>
        <label><span>案号</span><input v-model="caseNumber" placeholder="（示）沪 01 刑初 000 号" /></label>
        <label><span>涉嫌罪名</span><input v-model="charge" /></label>
        <label><span>管辖地区</span><input v-model="jurisdiction" /></label>
      </form>

      <div v-else-if="step === 2" class="empty-state">
        <strong>导入卷宗</strong>
        <p>上传、解析与 OCR 校对将在文档接口接通后启用。可将材料暂存于本地工作区。</p>
        <button class="button button-quiet" type="button" @click="toastPlaceholder">选择文件（占位）</button>
      </div>

      <div v-else-if="step === 3" class="empty-state">
        <strong>关联执行任务</strong>
        <p>案件创建后，可通过「执行任务」调用现有 <code>/v1/tasks</code> 引擎。本步仅保留入口。</p>
        <RouterLink class="button button-quiet" to="/tasks">打开执行任务</RouterLink>
      </div>

      <div v-else class="data-list">
        <div><dt>案件名称</dt><dd>{{ name || '—' }}</dd></div>
        <div><dt>当事人</dt><dd>{{ party || '—' }}</dd></div>
        <div><dt>案号</dt><dd>{{ caseNumber || '未填写' }}</dd></div>
        <div><dt>涉嫌罪名</dt><dd>{{ charge }}</dd></div>
        <div><dt>管辖</dt><dd>{{ jurisdiction }}</dd></div>
      </div>

      <div class="action-box">
        <button class="button button-quiet" :disabled="step === 1" type="button" @click="step -= 1">上一步</button>
        <button class="button button-primary" :disabled="!canNext" type="button" @click="next">
          {{ step === 4 ? '完成（占位）' : '下一步' }}
        </button>
      </div>
    </article>
  </div>
</template>
