<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ApiError, api } from '../api'
import type { ModelAccessConfigView, ResultPayload, TaskStatus, TaskView } from '../api-types'
import {
  errorHint,
  toModelAccessConfigUpdate,
  validate,
  type FieldErrors,
  type ModelAccessFormState,
} from '../lib/model-access-form'

type ProbeState = 'idle' | 'creating' | 'polling' | 'fetchingResult' | 'done'
type ProbeContent = {
  provider?: string
  model?: string
  latencyMs?: number
  schemaVersion?: string
}

const POLL_INTERVAL_MS = 2_000
const MAX_POLL_COUNT = 60
const TERMINAL_STATUSES: readonly TaskStatus[] = [
  'completed',
  'waiting_review',
  'failed',
  'timed_out',
  'rejected',
]

const CONFIG_FIELDS = [
  { label: '模型供应商', env: 'MODEL_PROVIDER' },
  { label: '模型名称', env: 'MODEL_NAME' },
  { label: 'API Base URL', env: 'MODEL_API_BASE_URL' },
  { label: 'API Key', env: 'MODEL_API_KEY' },
  { label: '超时秒数', env: 'MODEL_TIMEOUT_SECONDS' },
] as const

const PROBE_STATE_LABELS: Record<ProbeState, string> = {
  idle: '尚未验证',
  creating: '正在创建验证任务…',
  polling: '正在等待模型响应…',
  fetchingResult: '正在读取验证结果…',
  done: '验证已结束',
}

const route = useRoute()
const router = useRouter()

const form = reactive<ModelAccessFormState>({
  provider: 'stub',
  modelName: '',
  apiBaseUrl: '',
  apiKey: '',
  timeoutSeconds: '30',
})

const config = ref<ModelAccessConfigView | null>(null)
const loading = ref(true)
const loadError = ref('')
const validationErrors = ref<FieldErrors>({})
const saving = ref(false)
const saveError = ref('')
const saveSuccess = ref('')
const clearApiKey = ref(false)

const probeState = ref<ProbeState>('idle')
const probeTask = ref<TaskView | null>(null)
const probeResult = ref<ResultPayload | null>(null)
const probeError = ref('')
const pollCount = ref(0)

let pollTimer: number | undefined
let probeSequence = 0
let disposed = false

const apiKeyConfigured = computed(() => config.value?.apiKeyConfigured === true)
const isBusy = computed(() => (
  loading.value
  || saving.value
  || ['creating', 'polling', 'fetchingResult'].includes(probeState.value)
))
const probeContent = computed<ProbeContent | null>(() => {
  const content = probeResult.value?.content
  if (!content || typeof content !== 'object' || Array.isArray(content)) return null
  return content as ProbeContent
})
const probeFailed = computed(() => {
  const status = probeTask.value?.status
  return status === 'failed' || status === 'timed_out' || status === 'rejected'
})

function clearPollTimer() {
  if (pollTimer !== undefined) {
    window.clearTimeout(pollTimer)
    pollTimer = undefined
  }
}

function isActive(sequence: number) {
  return !disposed && sequence === probeSequence
}

function errorCode(caught: unknown): string | undefined {
  if (caught instanceof ApiError) return caught.code
  if (caught && typeof caught === 'object' && 'code' in caught) {
    const code = (caught as { code?: unknown }).code
    return typeof code === 'string' ? code : undefined
  }
  return undefined
}

function errorStatus(caught: unknown): number | undefined {
  if (caught instanceof ApiError) return caught.status
  if (caught && typeof caught === 'object' && 'status' in caught) {
    const status = (caught as { status?: unknown }).status
    return typeof status === 'number' ? status : undefined
  }
  return undefined
}

function withoutSecret(value: unknown, fallback: string) {
  const text = typeof value === 'string' && value.trim() ? value : fallback
  const secret = form.apiKey
  return secret ? text.split(secret).join('********') : text
}

function redirectToLogin() {
  void router.push({ name: 'login', query: { redirect: route.fullPath } })
}

function userError(caught: unknown, fallback: string) {
  if (errorStatus(caught) === 401) {
    redirectToLogin()
    return '会话已失效，请重新登录。'
  }

  switch (errorCode(caught)) {
    case 'MODEL_CONFIG_SEALED':
      return '服务端未配置配置加密密钥，暂不能保存 API Key。请联系运维配置 MODEL_CONFIG_ENCRYPTION_KEY 后重试。'
    case 'INVALID_MODEL_CONFIG':
      return '模型接入配置无效，请检查标红字段后重试。'
    case 'CLIENT_TIMEOUT':
      return '请求超时，请检查服务状态后重试。'
    case 'NETWORK_ERROR':
      return '网络连接失败，请确认本地服务可用。'
    default:
      return withoutSecret(caught instanceof Error ? caught.message : '', fallback)
  }
}

function resetApiKeyInput() {
  // API Key 只允许作为本次写入输入存在；读取和保存后都保持空值。
  form.apiKey = ''
}

async function loadConfig() {
  loading.value = true
  loadError.value = ''
  saveError.value = ''
  try {
    const current = await api.getModelAccessConfig()
    config.value = current
    form.provider = current.provider
    form.modelName = current.modelName
    form.apiBaseUrl = current.apiBaseUrl
    form.timeoutSeconds = String(current.timeoutSeconds)
    clearApiKey.value = false
    resetApiKeyInput()
  } catch (caught) {
    loadError.value = userError(caught, '模型接入配置读取失败。')
  } finally {
    loading.value = false
  }
}

function setValidationErrors() {
  const errors = validate(form, apiKeyConfigured.value)
  validationErrors.value = errors
  return Object.keys(errors).length === 0
}

async function saveConfig() {
  saveError.value = ''
  saveSuccess.value = ''
  if (saving.value || !setValidationErrors()) return

  saving.value = true
  try {
    const updated = await api.putModelAccessConfig(toModelAccessConfigUpdate(form, {
      clearApiKey: clearApiKey.value,
    }))
    config.value = updated
    form.provider = updated.provider
    form.modelName = updated.modelName
    form.apiBaseUrl = updated.apiBaseUrl
    form.timeoutSeconds = String(updated.timeoutSeconds)
    clearApiKey.value = false
    resetApiKeyInput()
    saveSuccess.value = '模型接入配置已保存；下一次模型调用将读取新的有效配置。'
  } catch (caught) {
    saveError.value = userError(caught, '模型接入配置保存失败。')
  } finally {
    saving.value = false
  }
}

function finishProbeWithError(message: string) {
  clearPollTimer()
  probeError.value = message
  probeState.value = 'done'
}

async function pollProbe(sequence: number) {
  if (!isActive(sequence) || !probeTask.value) return

  pollCount.value += 1
  try {
    const task = await api.getTask(probeTask.value.id)
    if (!isActive(sequence)) return
    probeTask.value = task

    if (task.status === 'completed') {
      clearPollTimer()
      probeState.value = 'fetchingResult'
      try {
        probeResult.value = await api.getTaskResult(task.id)
        if (!isActive(sequence)) return
        probeState.value = 'done'
      } catch (caught) {
        if (isActive(sequence)) finishProbeWithError(userError(caught, '验证结果读取失败。'))
      }
      return
    }

    if (TERMINAL_STATUSES.includes(task.status) || pollCount.value >= MAX_POLL_COUNT) {
      clearPollTimer()
      if (pollCount.value >= MAX_POLL_COUNT && !TERMINAL_STATUSES.includes(task.status)) {
        probeError.value = `连通性验证超时，最后状态：${task.status || '未知'}。`
      }
      probeState.value = 'done'
      return
    }

    pollTimer = window.setTimeout(() => {
      pollTimer = undefined
      void pollProbe(sequence)
    }, POLL_INTERVAL_MS)
  } catch (caught) {
    if (isActive(sequence)) finishProbeWithError(userError(caught, '任务状态读取失败。'))
  }
}

async function verifyConnectivity() {
  probeError.value = ''
  saveError.value = ''
  saveSuccess.value = ''
  if (isBusy.value || !setValidationErrors()) return

  clearPollTimer()
  probeSequence += 1
  const sequence = probeSequence
  probeState.value = 'creating'
  probeTask.value = null
  probeResult.value = null
  pollCount.value = 0

  try {
    const created = await api.createTask({
      query: '模型接入连通性验证',
      metadata: { taskType: 'model.probe' },
    })
    if (!isActive(sequence)) return
    probeTask.value = created
    probeState.value = 'polling'
    await pollProbe(sequence)
  } catch (caught) {
    if (isActive(sequence)) finishProbeWithError(userError(caught, '连通性验证任务创建失败。'))
  }
}

function toggleClearApiKey() {
  clearApiKey.value = !clearApiKey.value
  if (clearApiKey.value) form.apiKey = ''
}

onMounted(() => {
  resetApiKeyInput()
  void loadConfig()
})

onUnmounted(() => {
  disposed = true
  probeSequence += 1
  clearPollTimer()
})
</script>

<template>
  <div class="page-stack model-access-page">
    <header class="page-heading">
      <div>
        <RouterLink class="back-link" to="/settings">← 返回用户设置</RouterLink>
        <p class="eyebrow">系统设置</p>
        <h1>模型接入</h1>
        <p>填写模型接入参数并通过 Java 任务接口验证连通性。API Key 只写入服务端密文存储，不在页面结果中回显。</p>
      </div>
    </header>

    <div v-if="loading" class="panel empty-state" aria-live="polite">正在读取模型接入配置…</div>

    <div v-else-if="loadError" class="panel">
      <p class="notice notice-error" role="alert">{{ loadError }}</p>
      <button class="button button-quiet" type="button" @click="loadConfig">重新读取</button>
    </div>

    <template v-else>
      <section v-if="!apiKeyConfigured" class="notice notice-warning model-access-guide" role="note">
        <div>
          <strong>模型接入引导</strong>
          <p>当前尚未配置 API Key；桩模式（MODEL_PROVIDER=stub）下的验证结果不构成真实模型调用证据。</p>
          <ul>
            <li v-for="field in CONFIG_FIELDS" :key="field.env">
              <span>{{ field.label }}</span><code>{{ field.env }}</code>
            </li>
          </ul>
          <p v-if="config?.source === 'environment'">当前取值来自容器环境变量，尚无服务端保存记录。</p>
        </div>
      </section>

      <section class="panel model-access-form-panel">
        <div class="panel-heading">
          <div><p class="section-index">01</p><h2>模型接入配置</h2></div>
          <span v-if="apiKeyConfigured" class="subtle-chip" aria-label="API Key 已配置">API Key 已配置（********）</span>
        </div>
        <p class="panel-note">写入后由 Engine 在下一次模型调用前读取有效配置；未填写的新 API Key 不会被页面保存到本地文件。</p>

        <form class="form-stack" @submit.prevent="saveConfig">
          <label>
            <span>模型供应商 <b>*</b></span>
            <select v-model="form.provider" :disabled="isBusy" aria-label="模型供应商">
              <option value="stub">stub（桩模式）</option>
              <option value="openai">openai（真实模型）</option>
            </select>
            <small v-if="validationErrors.provider" class="field-error" role="alert">{{ validationErrors.provider }}</small>
          </label>

          <label>
            <span>模型名称 <b v-if="form.provider === 'openai'">*</b></span>
            <input v-model="form.modelName" :disabled="isBusy" autocomplete="off" placeholder="例如 gpt-4o-mini" />
            <small v-if="validationErrors.modelName" class="field-error" role="alert">{{ validationErrors.modelName }}</small>
          </label>

          <label>
            <span>API Base URL <b v-if="form.provider === 'openai'">*</b></span>
            <input v-model="form.apiBaseUrl" :disabled="isBusy" type="text" autocomplete="url" placeholder="https://api.example.com/v1" />
            <small v-if="validationErrors.apiBaseUrl" class="field-error" role="alert">{{ validationErrors.apiBaseUrl }}</small>
          </label>

          <label>
            <span>API Key <b v-if="form.provider === 'openai' && !apiKeyConfigured">*</b></span>
            <input
              v-model="form.apiKey"
              :disabled="isBusy || clearApiKey"
              type="password"
              autocomplete="off"
              placeholder="仅在变更或首次配置时填写"
            />
            <small v-if="apiKeyConfigured" class="field-note">服务端已配置：********；输入框保持为空。</small>
            <small v-else class="field-note">API Key 只用于本次保存请求，不会在读取接口中返回。</small>
            <small v-if="validationErrors.apiKey" class="field-error" role="alert">{{ validationErrors.apiKey }}</small>
          </label>

          <label>
            <span>超时秒数 <b>*</b></span>
            <input v-model="form.timeoutSeconds" :disabled="isBusy" type="text" inputmode="decimal" />
            <small v-if="validationErrors.timeoutSeconds" class="field-error" role="alert">{{ validationErrors.timeoutSeconds }}</small>
          </label>

          <div v-if="apiKeyConfigured" class="key-actions">
            <button
              class="button button-quiet"
              type="button"
              :disabled="isBusy"
              :aria-pressed="clearApiKey"
              @click="toggleClearApiKey"
            >
              {{ clearApiKey ? '取消清除已保存密钥' : '清除已保存密钥' }}
            </button>
            <small v-if="clearApiKey" class="field-note">保存时将发送空 API Key，清除服务端密文。</small>
          </div>

          <p v-if="saveError" class="notice notice-error" role="alert">{{ saveError }}</p>
          <p v-if="saveSuccess" class="notice notice-success" role="status">{{ saveSuccess }}</p>

          <div class="action-box model-access-actions">
            <p>保存配置后再发起验证，可确认当前 Engine 读取到的模型出口。</p>
            <div>
              <button class="button button-quiet" type="button" :disabled="isBusy" @click="verifyConnectivity">
                {{ probeState === 'creating' || probeState === 'polling' || probeState === 'fetchingResult' ? '验证中…' : '连通性验证' }}
              </button>
              <button class="button button-primary" type="submit" :disabled="isBusy">
                {{ saving ? '保存中…' : '保存配置' }}
              </button>
            </div>
          </div>
        </form>
      </section>

      <section class="panel probe-panel" aria-live="polite">
        <div class="panel-heading">
          <div><p class="section-index">02</p><h2>连通性验证</h2></div>
          <span class="subtle-chip">{{ PROBE_STATE_LABELS[probeState] }}</span>
        </div>
        <p v-if="probeState === 'idle'" class="panel-note">点击「连通性验证」后，页面会创建 `model.probe` 任务并每 2 秒读取一次状态，最多读取 60 次。</p>
        <p v-else-if="probeState === 'polling'" class="subtle-text">任务 {{ probeTask?.id || '—' }} · 已读取 {{ pollCount }}/{{ MAX_POLL_COUNT }} 次 · {{ probeTask?.currentStage || '排队中' }}</p>
        <p v-else-if="probeState === 'fetchingResult'" class="subtle-text">任务已完成，正在读取结果内容。</p>
        <p v-if="probeError" class="notice notice-error" role="alert">{{ probeError }}</p>

        <div v-if="probeFailed" class="notice notice-error" role="alert">
          <strong>{{ probeTask?.errorCode || 'MODEL_FAILED' }}</strong>
          <span>{{ withoutSecret(probeTask?.error, '模型探针任务未成功完成。') }}</span>
          <span>{{ errorHint(probeTask?.errorCode) }}</span>
        </div>

        <template v-if="probeState === 'done' && probeTask?.status === 'completed' && probeContent">
          <dl class="data-list probe-result-list">
            <div><dt>provider</dt><dd>{{ probeContent.provider || '—' }}</dd></div>
            <div><dt>model</dt><dd>{{ probeContent.model || '—' }}</dd></div>
            <div><dt>latencyMs</dt><dd>{{ probeContent.latencyMs ?? '—' }}</dd></div>
            <div><dt>schemaVersion</dt><dd>{{ probeContent.schemaVersion || '—' }}</dd></div>
          </dl>
          <p v-if="probeContent.provider === 'stub'" class="notice notice-warning" role="note">
            <strong>桩响应</strong>
            <span>该结果为桩响应，不构成真实模型调用证据。</span>
          </p>
        </template>

        <p v-if="probeState === 'done' && probeTask && !probeFailed && probeTask.status !== 'completed' && !probeError" class="notice notice-error" role="alert">
          验证未完成：{{ probeTask.status }}。
        </p>
      </section>
    </template>
  </div>
</template>

<style scoped>
.model-access-page { width: min(100%, 960px); }
.model-access-guide { display: block; }
.model-access-guide p { margin: 8px 0 0; }
.model-access-guide ul { display: grid; gap: 7px; margin: 12px 0 0; padding-left: 20px; }
.model-access-guide li { display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: baseline; }
.model-access-guide li span { min-width: 86px; }
.model-access-guide code { color: var(--lc-brand-800); font-size: 11px; }
.field-error { color: var(--lc-risk); font-size: 11px; font-weight: 600; }
.field-note { color: var(--lc-muted); font-size: 11px; font-weight: 500; line-height: 1.5; }
.key-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
.model-access-actions { align-items: flex-end; }
.model-access-actions > div { display: flex; flex-wrap: wrap; gap: 10px; }
.probe-panel { min-height: 250px; }
.probe-result-list { margin-bottom: 18px; }
.subtle-text { margin: 0; color: var(--lc-muted); font-size: 12px; }
@media (max-width: 640px) {
  .model-access-actions { align-items: stretch; }
  .model-access-actions > div { width: 100%; }
  .model-access-actions button { flex: 1; }
}
</style>
