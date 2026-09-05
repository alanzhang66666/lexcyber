<script setup lang="ts">
import { onMounted, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { logout } from '../lib/auth'
import { DEFAULT_SETTINGS, applySettings, loadSettings, saveSettings, type UiSettings } from '../lib/ui-settings'

const router = useRouter()
const settings = reactive<UiSettings>({ ...DEFAULT_SETTINGS })

onMounted(() => {
  Object.assign(settings, loadSettings())
  applySettings(settings)
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
        <p>主题、导航布局与内容密度保存在本浏览器。首页始终使用顶部导航。</p>
      </div>
      <RouterLink class="button button-quiet" to="/">返回首页</RouterLink>
    </header>
    <section class="settings-layout">
      <article class="panel">
        <div class="panel-heading"><div><p class="section-index">01</p><h2>界面主题</h2></div></div>
        <div class="theme-grid">
          <button type="button" class="theme-choice" :class="{ selected: settings.theme === 'aurora' }" @click="update('theme', 'aurora')">
            <b>极光衡链</b><small>默认方案</small>
          </button>
          <button type="button" class="theme-choice" :class="{ selected: settings.theme === 'ember' }" @click="update('theme', 'ember')">
            <b>朱砂曜金</b><small>温暖而正式</small>
          </button>
          <button type="button" class="theme-choice" :class="{ selected: settings.theme === 'tide' }" @click="update('theme', 'tide')">
            <b>深海青</b><small>冷静与技术感</small>
          </button>
        </div>
      </article>
      <article class="panel">
        <div class="panel-heading"><div><p class="section-index">02</p><h2>导航与密度</h2></div></div>
        <label class="check-row">
          <input :checked="settings.layout === 'top'" type="radio" name="layout" @change="update('layout', 'top')" />
          <span><strong>顶部导航</strong><small>首页与工作页均使用顶栏。</small></span>
        </label>
        <label class="check-row">
          <input :checked="settings.layout === 'side'" type="radio" name="layout" @change="update('layout', 'side')" />
          <span><strong>工作区侧栏</strong><small>仅在案件、阅卷、分析、复核页显示；首页不出现侧栏。</small></span>
        </label>
        <div class="segmented" role="group" aria-label="内容密度">
          <button type="button" :class="{ 'is-active': settings.density === 'compact' }" @click="update('density', 'compact')">紧凑</button>
          <button type="button" :class="{ 'is-active': settings.density === 'comfortable' }" @click="update('density', 'comfortable')">舒适</button>
          <button type="button" :class="{ 'is-active': settings.density === 'spacious' }" @click="update('density', 'spacious')">宽松</button>
        </div>
      </article>
      <article class="panel">
        <div class="panel-heading"><div><p class="section-index">03</p><h2>账号</h2></div></div>
        <p class="panel-note">当前会话保存在本浏览器。退出后需重新登录才能进入系统。</p>
        <button class="button button-quiet" type="button" @click="signOut">退出登录</button>
      </article>
      <article class="panel empty-state">
        <strong>通知与安全策略</strong>
        <p>通知渠道、设备会话与正式身份提供方将在服务端认证接通后配置。</p>
      </article>
    </section>
  </div>
</template>
