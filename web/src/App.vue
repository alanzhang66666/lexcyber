<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import { lastCaseId } from './data/placeholder-cases'
import { logout, refreshSession, session } from './lib/auth'
import { onToast, toastPlaceholder } from './lib/toast'
import { applySettings, loadSettings } from './lib/ui-settings'

const route = useRoute()
const router = useRouter()
const moreOpen = ref(false)
const profileOpen = ref(false)
const toastMessage = ref('')
const layout = ref(loadSettings().layout)
let stopToast: (() => void) | undefined
let timer: number | undefined

const docketTo = computed(() => `/cases/${lastCaseId()}/docket`)
const analysisTo = computed(() => `/cases/${lastCaseId()}/analysis`)
const showDock = computed(() => (
  layout.value === 'side'
  && route.name !== 'home'
  && route.name !== 'settings'
  && route.name !== 'login'
))

const moreActive = computed(() => ['sources', 'rules', 'tasks', 'task-detail', 'audit'].includes(String(route.name)))
const signedIn = computed(() => Boolean(session.value))
const homeActive = computed(() => route.path === '/')
const authActive = computed(() => route.name === 'login')
const displayName = computed(() => session.value?.displayName || '未登录')
const avatarText = computed(() => displayName.value.slice(0, 1))

async function signOut() {
  profileOpen.value = false
  await logout()
  void router.push({ name: 'home' })
}
const casesActive = computed(() => route.path === '/cases' || route.path === '/cases/new' || /^\/cases\/[^/]+$/.test(route.path))
const docketActive = computed(() => route.path.includes('/docket'))
const analysisActive = computed(() => route.path.includes('/analysis'))
const reviewsActive = computed(() => route.path.startsWith('/reviews'))

function refreshLayout() {
  layout.value = loadSettings().layout
}

onMounted(() => {
  applySettings(loadSettings())
  void refreshSession()
  stopToast = onToast((message) => {
    toastMessage.value = message
    window.clearTimeout(timer)
    timer = window.setTimeout(() => { toastMessage.value = '' }, 2800)
  })
  window.addEventListener('lexcyber-settings', refreshLayout)
})

onUnmounted(() => {
  stopToast?.()
  window.clearTimeout(timer)
  window.removeEventListener('lexcyber-settings', refreshLayout)
})

watch(() => route.path, () => {
  moreOpen.value = false
  profileOpen.value = false
})
</script>

<template>
  <div class="app-shell" :class="{ 'has-dock': showDock, 'is-home': homeActive, 'is-auth': authActive }">
    <a class="skip-link" href="#main-content">跳到主要内容</a>
    <header class="topbar">
      <RouterLink class="brand" to="/" aria-label="LexCyber 网域衡鉴首页">
        <span class="brand-mark" aria-hidden="true"><i></i><b>衡</b></span>
        <span class="brand-copy">
          <strong>LexCyber <em>网域衡鉴</em></strong>
        </span>
      </RouterLink>
      <nav v-if="!authActive" class="primary-nav" aria-label="主要导航">
        <RouterLink to="/" active-class="" exact-active-class="" :class="{ 'router-link-active': homeActive }">首页</RouterLink>
        <RouterLink to="/cases" active-class="" exact-active-class="" :class="{ 'router-link-active': casesActive }">案件中心</RouterLink>
        <RouterLink :to="docketTo" active-class="" exact-active-class="" :class="{ 'router-link-active': docketActive }">智能阅卷</RouterLink>
        <RouterLink :to="analysisTo" active-class="" exact-active-class="" :class="{ 'router-link-active': analysisActive }">量刑分析</RouterLink>
        <RouterLink to="/reviews" active-class="" exact-active-class="" :class="{ 'router-link-active': reviewsActive }">人工复核</RouterLink>
        <div class="more-nav">
          <button :class="{ 'router-link-active': moreOpen || moreActive }" type="button" @click="moreOpen = !moreOpen">更多</button>
          <div v-if="moreOpen" class="more-menu">
            <RouterLink to="/sources">法源与类案</RouterLink>
            <RouterLink to="/rules">量刑规则</RouterLink>
            <RouterLink to="/tasks">执行任务</RouterLink>
            <RouterLink to="/audit">统计与审计</RouterLink>
          </div>
        </div>
      </nav>
      <div v-if="!authActive" class="top-actions">
        <label v-if="signedIn" class="home-search">
          <span aria-hidden="true">⌕</span>
          <input
            type="search"
            placeholder="搜索案件、法源、规则、报告…"
            @keydown.enter.prevent="toastPlaceholder"
          />
        </label>
        <template v-if="signedIn">
          <button class="icon-action work-search" type="button" @click="toastPlaceholder">搜索</button>
          <button class="icon-action work-notice" type="button" @click="toastPlaceholder">通知</button>
          <div class="profile-menu">
            <button class="profile-link" type="button" @click="profileOpen = !profileOpen">
              <span>{{ avatarText }}</span>
              <div><small>当前用户</small><strong>{{ displayName }}</strong></div>
            </button>
            <div v-if="profileOpen" class="more-menu profile-dropdown">
              <RouterLink to="/settings">用户设置</RouterLink>
              <button type="button" @click="signOut">退出登录</button>
            </div>
          </div>
          <div class="environment" title="当前连接本地开发服务">
            <span aria-hidden="true"></span>
            <div><small>运行环境</small><strong>LOCAL</strong></div>
          </div>
        </template>
        <RouterLink v-else class="home-btn home-btn-primary" to="/login">登录</RouterLink>
      </div>
    </header>
    <aside v-if="showDock" class="workspace-dock" aria-label="工作区侧栏">
      <RouterLink to="/cases">案件列表</RouterLink>
      <RouterLink :to="docketTo">卷宗阅览</RouterLink>
      <RouterLink :to="analysisTo">量刑分析</RouterLink>
      <RouterLink to="/reviews">人工复核</RouterLink>
    </aside>
    <main id="main-content" class="main-content" tabindex="-1">
      <RouterView />
    </main>
    <footer class="app-footer">
      <span>LexCyber 网域衡鉴 · 涉外互联网犯罪刑事合规与量刑辅助</span>
      <span>辅助研判，不替代司法裁量</span>
    </footer>
    <div v-if="toastMessage" class="app-toast" role="status" aria-live="polite">{{ toastMessage }}</div>
  </div>
</template>
