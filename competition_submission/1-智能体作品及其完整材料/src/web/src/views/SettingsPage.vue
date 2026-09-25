<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ApiError, api } from '../api'
import type { ModelAccessConfigView, ResultPayload, TaskView } from '../api-types'
import { logout } from '../lib/auth'
import {
  toModelAccessConfigUpdate,
  validate,
  type FieldErrors,
  type ModelAccessFormState,
} from '../lib/model-access-form'
import { DEFAULT_SETTINGS, applySettings, loadSettings, saveSettings, type UiSettings } from '../lib/ui-settings'

const router = useRouter()
const settings = reactive<UiSettings>({ ...DEFAULT_SETTINGS })
const modelForm = reactive<ModelAccessFormState>({
  provider: 'openai',
  modelName: '',
  apiBaseUrl: 'https://api.openai.com/v1',
  apiKey: '',
  timeoutSeconds: '45',
})
const modelConfig = ref<ModelAccessConfigView | null>(null)
const modelLoading = ref(true)
const modelSaving = ref(false)
const modelErrors = ref<FieldErrors>({})
const modelMessage = ref('')
const modelError = ref('')
const clearApiKey = ref(false)
const probeTask = ref<TaskView | null>(null)
const probeResult = ref<ResultPayload | null>(null)
const probeBusy = ref(false)
const probeError = ref('')
let probeTimer: number | undefined
let disposed = false

const apiKeyConfigured = computed(() => modelConfig.value?.apiKeyConfigured === true)
const modelBusy = computed(() => modelLoading.value || modelSaving.value || probeBusy.value)
const probeContent = computed(() => {
  const content = probeResult.value?.content
  return content && typeof content === 'object' && !Array.isArray(content)
    ? content as Record<string, unknown>
    : null
})

function readableError(caught: unknown, fallback: string) {
  if (caught instanceof ApiError && caught.code === 'MODEL_CONFIG_SEALED') {
    return '服务端未配置 MODEL_CONFIG_ENCRYPTION_KEY，暂不能保存 API Key。'
  }
  return caught instanceof Error && caught.message ? caught.message : fallback
}

async function loadModelConfig() {
  modelLoading.value = true
  modelError.value = ''
  try {
    const current = await api.getModelAccessConfig()
    modelConfig.value = current
    modelForm.provider = current.provider
    modelForm.modelName = current.modelName
    modelForm.apiBaseUrl = current.apiBaseUrl
    modelForm.timeoutSeconds = String(current.timeoutSeconds)
    modelForm.apiKey = ''
    clearApiKey.value = false
  } catch (caught) {
    modelError.value = readableError(caught, '模型配置读取失败。')
  } finally {
    modelLoading.value = false
  }
}

async function saveModelConfig() {
  modelErrors.value = validate(modelForm, apiKeyConfigured.value && !clearApiKey.value)
  modelMessage.value = ''
  modelError.value = ''
  if (Object.keys(modelErrors.value).length) return false
  modelSaving.value = true
  try {
    const updated = await api.putModelAccessConfig(
      toModelAccessConfigUpdate(modelForm, clearApiKey.value),
    )
    modelConfig.value = updated
    modelForm.apiKey = ''
    clearApiKey.value = false
    modelMessage.value = '模型 API 配置已保存，后续任务将读取新的有效配置。'
    return true
  } catch (caught) {
    modelError.value = readableError(caught, '模型配置保存失败。')
    return false
  } finally {
    modelSaving.value = false
  }
}

function clearProbeTimer() {
  if (probeTimer !== undefined) window.clearTimeout(probeTimer)
  probeTimer = undefined
}

async function pollProbe(taskId: string, count = 0) {
  if (disposed || count >= 60) {
    probeBusy.value = false
    probeError.value = '验证等待超时，请稍后到任务中心查看。'
    return
  }
  try {
    const task = await api.getTask(taskId)
    if (disposed) return
    probeTask.value = task
    if (task.status === 'completed') {
      probeResult.value = await api.getTaskResult(taskId)
      probeBusy.value = false
      return
    }
    if (['failed', 'timed_out', 'rejected'].includes(task.status)) {
      probeBusy.value = false
      probeError.value = `${task.errorCode || 'MODEL_FAILED'}：${task.error || '模型连通性验证失败。'}`
      return
    }
    probeTimer = window.setTimeout(() => void pollProbe(taskId, count + 1), 1500)
  } catch (caught) {
    probeBusy.value = false
    probeError.value = readableError(caught, '验证任务读取失败。')
  }
}

async function verifyModel() {
  probeBusy.value = true
  probeError.value = ''
  probeTask.value = null
  probeResult.value = null
  try {
    const task = await api.createTask({ query: '模型接入连通性验证', metadata: { taskType: 'model.probe' } })
    probeTask.value = task
    await pollProbe(task.id)
  } catch (caught) {
    probeBusy.value = false
    probeError.value = readableError(caught, '无法创建验证任务。')
  }
}

onMounted(() => {
  Object.assign(settings, loadSettings())
  applySettings(settings)
  void loadModelConfig()
})

onUnmounted(() => {
  disposed = true
  clearProbeTimer()
})

async function signOut() {
  await logout()
  void router.push({ name: 'home' })
}

function update<K extends keyof UiSettings>(key: K, value: UiSettings[K]) {
  settings[key] = value
  saveSettings({ ...settings })
}
</script>

<template>
  <div class="page-stack">
    <header class="page-heading">
      <div>
        <p class="eyebrow">用户设置</p>
        <h1>用户设置</h1>
        <p>管理界面偏好、模型 API 接入与当前账号会话。</p>
      </div>
      <RouterLink class="button button-quiet" to="/">返回首页</RouterLink>
    </header>

    <section class="settings-layout">
      <article class="panel">
        <div class="panel-heading"><div><p class="section-index">01</p><h2>界面主题</h2></div></div>
        <div class="theme-grid">
          <button type="button" class="theme-choice" :class="{ selected: settings.theme === 'aurora' }" @click="update('theme', 'aurora')"><b>极光衡链</b><small>默认方案</small></button>
          <button type="button" class="theme-choice" :class="{ selected: settings.theme === 'ember' }" @click="update('theme', 'ember')"><b>朱砂曜金</b><small>温暖而正式</small></button>
          <button type="button" class="theme-choice" :class="{ selected: settings.theme === 'tide' }" @click="update('theme', 'tide')"><b>深海青</b><small>冷静与技术感</small></button>
        </div>
      </article>

      <article class="panel">
        <div class="panel-heading"><div><p class="section-index">02</p><h2>内容密度</h2></div></div>
        <div class="segmented" role="group" aria-label="内容密度">
          <button type="button" :class="{ 'is-active': settings.density === 'compact' }" @click="update('density', 'compact')">紧凑</button>
          <button type="button" :class="{ 'is-active': settings.density === 'comfortable' }" @click="update('density', 'comfortable')">舒适</button>
          <button type="button" :class="{ 'is-active': settings.density === 'spacious' }" @click="update('density', 'spacious')">宽松</button>
        </div>
      </article>

      <article class="panel model-settings">
        <div class="panel-heading">
          <div><p class="section-index">03</p><h2>模型 API 接入</h2></div>
          <span class="subtle-chip">{{ apiKeyConfigured ? 'API Key 已配置 · ********' : 'API Key 未配置' }}</span>
        </div>
        <p class="panel-note">配置通过 Java 接口保存，API Key 使用密文存储且不会从读取接口回显。Engine 会在下一次模型调用时读取最新值。</p>

        <div v-if="modelLoading" class="empty-state">正在读取模型配置…</div>
        <form v-else class="form-stack" @submit.prevent="saveModelConfig">
          <label>
            <span>供应商</span>
            <select v-model="modelForm.provider" :disabled="modelBusy">
              <option value="openai">OpenAI 兼容接口</option>
              <option value="stub">Stub（仅开发验证）</option>
            </select>
            <small v-if="modelErrors.provider" class="field-error">{{ modelErrors.provider }}</small>
          </label>
          <label>
            <span>模型名称</span>
            <input v-model="modelForm.modelName" :disabled="modelBusy" autocomplete="off" placeholder="例如 deepseek-chat / gpt-4.1-mini" />
            <small v-if="modelErrors.modelName" class="field-error">{{ modelErrors.modelName }}</small>
          </label>
          <label>
            <span>API Base URL</span>
            <input v-model="modelForm.apiBaseUrl" :disabled="modelBusy" autocomplete="url" placeholder="https://api.example.com/v1" />
            <small v-if="modelErrors.apiBaseUrl" class="field-error">{{ modelErrors.apiBaseUrl }}</small>
          </label>
          <label>
            <span>API Key</span>
            <input v-model="modelForm.apiKey" :disabled="modelBusy || clearApiKey" type="password" autocomplete="new-password" placeholder="仅首次配置或更换时填写" />
            <small class="field-note">{{ apiKeyConfigured ? '已保存密钥不会回显；留空表示保持不变。' : '密钥只随本次保存请求发送。' }}</small>
            <small v-if="modelErrors.apiKey" class="field-error">{{ modelErrors.apiKey }}</small>
          </label>
          <label>
            <span>请求超时（秒）</span>
            <input v-model="modelForm.timeoutSeconds" :disabled="modelBusy" type="number" min="1" max="600" step="1" />
            <small v-if="modelErrors.timeoutSeconds" class="field-error">{{ modelErrors.timeoutSeconds }}</small>
          </label>
          <label v-if="apiKeyConfigured" class="check-row">
            <input v-model="clearApiKey" :disabled="modelBusy" type="checkbox" />
            <span>保存时清除服务端已存 API Key</span>
          </label>

          <p v-if="modelError" class="notice notice-error" role="alert">{{ modelError }}</p>
          <p v-if="modelMessage" class="notice notice-success" role="status">{{ modelMessage }}</p>
          <div class="action-box model-actions">
            <p>请先保存，再执行连通性验证；验证会创建一条可审计的 model.probe 任务。</p>
            <div>
              <button class="button button-quiet" type="button" :disabled="modelBusy" @click="verifyModel">{{ probeBusy ? '验证中…' : '连通性验证' }}</button>
              <button class="button button-primary" type="submit" :disabled="modelBusy">{{ modelSaving ? '保存中…' : '保存配置' }}</button>
            </div>
          </div>
          <p v-if="probeError" class="notice notice-error" role="alert">{{ probeError }}</p>
          <dl v-if="probeContent" class="data-list probe-result">
            <div><dt>供应商</dt><dd>{{ probeContent.provider || '—' }}</dd></div>
            <div><dt>模型</dt><dd>{{ probeContent.model || '—' }}</dd></div>
            <div><dt>延迟</dt><dd>{{ probeContent.latencyMs ?? '—' }} ms</dd></div>
          </dl>
        </form>
      </article>

      <article class="panel">
        <div class="panel-heading"><div><p class="section-index">04</p><h2>账号</h2></div></div>
        <p class="panel-note">当前会话保存在本浏览器。退出后需重新登录才能进入系统。</p>
        <button class="button button-quiet" type="button" @click="signOut">退出登录</button>
      </article>
    </section>
  </div>
</template>

<style scoped>
.model-settings { grid-column: 1 / -1; }
.model-settings .form-stack { max-width: 760px; }
.field-note { color: var(--lc-muted); font-size: 11px; font-weight: 400; }
.field-error { color: var(--lc-risk); font-size: 11px; font-weight: 600; }
.model-actions > div { display: flex; flex-wrap: wrap; gap: 10px; }
.probe-result { margin-top: 4px; }
@media (max-width: 720px) {
  .model-actions { align-items: stretch; flex-direction: column; }
  .model-actions > div, .model-actions button { width: 100%; }
}
</style>
