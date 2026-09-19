<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import BrandMark from './components/BrandMark.vue'
import { CORE_MODULES, modulePath } from './data/modules'
import { currentCaseId, resolveT1CaseId, syncCurrentCaseFromStorage } from './lib/current-case'
import { logout, refreshSession, session } from './lib/auth'
import { onToast } from './lib/toast'
import { applySettings, loadSettings } from './lib/ui-settings'

const route = useRoute()
const router = useRouter()
const profileOpen = ref(false)
const functionsOpen = ref(false)
const functionsTrigger = ref<HTMLButtonElement | null>(null)
const functionsMenuStyle = ref<Record<string, string>>({})
const toastMessage = ref('')
const searchQuery = ref('')
let stopToast: (() => void) | undefined
let timer: number | undefined

const functionEntries = computed(() => CORE_MODULES.map((module) => ({
  ...module,
  to: modulePath(module, currentCaseId.value),
})))

const signedIn = computed(() => Boolean(session.value))
const homeActive = computed(() => route.path === '/')
const functionsActive = computed(() => {
  const path = route.path
  return path === '/reviews'
    || path.startsWith('/reviews/')
    || /\/cases\/[^/]+\/(compliance|conviction|analysis)$/.test(path)
})
const aboutActive = computed(() => route.path === '/about')
const authActive = computed(() => route.name === 'login')
const displayName = computed(() => session.value?.displayName || '未登录')
const avatarText = computed(() => displayName.value.slice(0, 1))

async function toggleFunctions() {
  functionsOpen.value = !functionsOpen.value
  profileOpen.value = false
  if (!functionsOpen.value) return
  await nextTick()
  const box = functionsTrigger.value?.getBoundingClientRect()
  if (!box) return
  functionsMenuStyle.value = {
    top: `${Math.round(box.bottom + 8)}px`,
    left: `${Math.round(box.left)}px`,
  }
}

function toggleProfile() {
  profileOpen.value = !profileOpen.value
  functionsOpen.value = false
}

function goSearch() {
  const q = searchQuery.value.trim()
  if (!q) {
    void router.push('/cases')
    return
  }
  void router.push({ path: '/sources', query: { q } })
}

async function signOut() {
  profileOpen.value = false
  functionsOpen.value = false
  await logout()
  void router.push({ name: 'home' })
}
const casesActive = computed(() => (
  route.path === '/cases'
  || route.path === '/cases/new'
  || /^\/cases\/[^/]+$/.test(route.path)
  || /^\/cases\/[^/]+\/docket$/.test(route.path)
  || /^\/cases\/[^/]+\/documents$/.test(route.path)
))

onMounted(() => {
  applySettings(loadSettings())
  void refreshSession()
  void resolveT1CaseId()
  stopToast = onToast((message) => {
    toastMessage.value = message
    window.clearTimeout(timer)
    timer = window.setTimeout(() => { toastMessage.value = '' }, 2800)
  })
})

onUnmounted(() => {
  stopToast?.()
  window.clearTimeout(timer)
})

watch(() => route.path, () => {
  profileOpen.value = false
  functionsOpen.value = false
  syncCurrentCaseFromStorage()
})
</script>

<template>
  <!-- 所有非登录页统一使用浅色顶栏（与首页一致）；登录页仍走 is-auth -->
  <div class="app-shell" :class="{ 'is-home': !authActive, 'is-auth': authActive }">
    <a class="skip-link" href="#main-content">跳到主要内容</a>
    <header class="topbar">
      <RouterLink class="brand" to="/" aria-label="LexCyber 网域衡鉴首页">
        <BrandMark />
        <span class="brand-copy">
          <strong>Lex<em>Cyber</em> 网域衡鉴</strong>
        </span>
      </RouterLink>
      <nav v-if="!authActive" class="primary-nav" aria-label="主要导航">
        <RouterLink to="/" active-class="" exact-active-class="" :class="{ 'router-link-active': homeActive }">首页</RouterLink>
        <div class="more-nav">
          <button
            ref="functionsTrigger"
            type="button"
            aria-haspopup="menu"
            aria-controls="functions-menu"
            :aria-expanded="functionsOpen"
            :class="{ 'router-link-active': functionsActive }"
            @click="toggleFunctions"
          >功能中心</button>
          <Teleport to="body">
            <div
              v-if="functionsOpen"
              id="functions-menu"
              class="more-menu functions-flyout"
              role="menu"
              :style="functionsMenuStyle"
            >
              <RouterLink
                v-for="item in functionEntries"
                :key="item.key"
                role="menuitem"
                :to="item.to"
              >{{ item.title }}</RouterLink>
            </div>
          </Teleport>
        </div>
        <RouterLink to="/cases" active-class="" exact-active-class="" :class="{ 'router-link-active': casesActive }">案件中心</RouterLink>
        <RouterLink to="/about" active-class="" exact-active-class="" :class="{ 'router-link-active': aboutActive }">关于我们</RouterLink>
      </nav>
      <div v-if="!authActive" class="top-actions">
        <label v-if="signedIn" class="home-search">
          <span aria-hidden="true">⌕</span>
          <input
            v-model="searchQuery"
            type="search"
            placeholder="搜索法源、关键词…"
            @keydown.enter.prevent="goSearch"
          />
        </label>
        <template v-if="signedIn">
          <button class="icon-action work-search" type="button" @click="goSearch">搜索</button>
          <RouterLink class="icon-action work-notice" to="/reviews">复核</RouterLink>
          <div class="profile-menu">
            <button class="profile-link" type="button" @click="toggleProfile">
              <span>{{ avatarText }}</span>
              <div><small>当前用户</small><strong>{{ displayName }}</strong></div>
            </button>
            <div v-if="profileOpen" class="more-menu profile-dropdown">
              <RouterLink to="/settings">用户设置</RouterLink>
              <button type="button" @click="signOut">退出登录</button>
            </div>
          </div>
        </template>
        <RouterLink v-else class="home-btn home-btn-primary" to="/login">登录</RouterLink>
      </div>
    </header>
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
