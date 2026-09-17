<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import logoUrl from '../assets/logo.png'
import { loginAccount, registerAccount, safeRedirect } from '../lib/auth'

const route = useRoute()
const router = useRouter()
const mode = ref<'login' | 'register'>('login')
const username = ref('')
const displayName = ref('')
const password = ref('')
const confirm = ref('')
const error = ref('')
const submitting = ref(false)

const title = computed(() => mode.value === 'login' ? '登录' : '注册')

function switchMode(next: 'login' | 'register') {
  mode.value = next
  error.value = ''
}

async function submit() {
  error.value = ''
  submitting.value = true
  try {
    if (mode.value === 'register') {
      if (password.value !== confirm.value) throw new Error('两次输入的密码不一致。')
      await registerAccount({ username: username.value, displayName: displayName.value, password: password.value })
    } else {
      await loginAccount(username.value, password.value)
    }
    await router.replace(safeRedirect(route.query.redirect))
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '无法完成该操作。'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="auth-page">
    <section class="auth-card">
      <div class="auth-brand">
        <img class="brand-mark" :src="logoUrl" alt="" />
        <strong>LexCyber 网域衡鉴</strong>
        <p>涉外互联网犯罪刑事合规与量刑辅助系统</p>
      </div>
      <div class="auth-tabs" role="tablist" aria-label="登录或注册">
        <button type="button" role="tab" :aria-selected="mode === 'login'" :class="{ 'is-active': mode === 'login' }" @click="switchMode('login')">登录</button>
        <button type="button" role="tab" :aria-selected="mode === 'register'" :class="{ 'is-active': mode === 'register' }" @click="switchMode('register')">注册</button>
      </div>
      <form class="form-stack" @submit.prevent="submit">
        <label>
          <span>账号 <b aria-hidden="true">*</b></span>
          <input v-model="username" autocomplete="username" required maxlength="32" placeholder="字母、数字或下划线" />
        </label>
        <label v-if="mode === 'register'">
          <span>显示名称</span>
          <input v-model="displayName" autocomplete="nickname" maxlength="32" placeholder="可选，默认与账号相同" />
        </label>
        <label>
          <span>密码 <b aria-hidden="true">*</b></span>
          <input v-model="password" type="password" :autocomplete="mode === 'login' ? 'current-password' : 'new-password'" required minlength="8" placeholder="至少 8 位" />
        </label>
        <label v-if="mode === 'register'">
          <span>确认密码 <b aria-hidden="true">*</b></span>
          <input v-model="confirm" type="password" autocomplete="new-password" required minlength="8" />
        </label>
        <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
        <button class="button button-primary" :disabled="submitting || !username.trim() || password.length < 8" type="submit">
          {{ submitting ? '正在处理…' : title }}
        </button>
      </form>
      <p class="auth-note">未登录可浏览首页。账号由 Java 身份接口签发并校验，工作台需登录后进入。</p>
    </section>
  </div>
</template>
