<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'

const router = useRouter()
const title = ref('')
const jurisdiction = ref('CN')
const asOfDate = ref('')
const submitting = ref(false)
const error = ref('')

async function submit() {
  error.value = ''
  submitting.value = true
  try {
    const created = await api.createCase({
      title: title.value.trim(),
      ...(jurisdiction.value.trim() ? { jurisdiction: jurisdiction.value.trim() } : {}),
      ...(asOfDate.value ? { asOfDate: asOfDate.value } : {}),
    })
    await router.push(`/cases/${created.id}`)
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '案件创建失败。'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="page-stack narrow-stack">
    <header class="page-heading">
      <div>
        <RouterLink class="back-link" to="/cases">← 返回案件中心</RouterLink>
        <p class="eyebrow">新建案件</p>
        <h1>新建案件</h1>
        <p>创建案件后，可在案件工作区上传材料并发起解析。</p>
      </div>
    </header>
    <article class="panel">
      <form class="form-stack" @submit.prevent="submit">
        <label>
          <span>案件名称 <b>*</b></span>
          <input v-model="title" required placeholder="例如：林某涉嫌跨境电信网络诈骗" />
        </label>
        <label>
          <span>法域</span>
          <input v-model="jurisdiction" placeholder="例如：CN" />
        </label>
        <label>
          <span>基准日期</span>
          <input v-model="asOfDate" type="date" />
        </label>
        <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
        <button class="button button-primary" type="submit" :disabled="submitting || !title.trim()">
          {{ submitting ? '正在创建…' : '创建案件' }}
        </button>
      </form>
    </article>
  </div>
</template>
