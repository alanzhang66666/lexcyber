<script setup lang="ts">
import { computed, ref } from 'vue'

type CaseStatus = '分析中' | '待复核' | '已归档'
type CaseItem = { id: string; title: string; status: CaseStatus; progress: number; risk: string }

const activePage = ref<'home' | 'settings'>('home')
const sidebarEnabled = ref(false)
const cases = ref<CaseItem[]>([
  { id: 'LC-2026-0048', title: '危险驾驶罪量刑辅助分析', status: '待复核', progress: 82, risk: '中风险' },
  { id: 'LC-2026-0046', title: '合同诈骗事实链整理', status: '分析中', progress: 48, risk: '低风险' },
  { id: 'LC-2026-0039', title: '共同犯罪作用认定', status: '已归档', progress: 100, risk: '低风险' },
])

const pageTitle = computed(() => activePage.value === 'home' ? '量刑工作台' : '用户设置')
function toggleSidebar() {
  sidebarEnabled.value = !sidebarEnabled.value
}
</script>

<template>
  <div class="app-shell" :class="{ 'with-sidebar': sidebarEnabled && activePage !== 'home' }">
    <header class="topbar">
      <button class="brand" type="button" @click="activePage = 'home'" aria-label="返回 LexCyber 首页">
        <span class="brand-mark"><span></span><i></i><b></b></span>
        <span><strong>LexCyber</strong><small>证据有源 · 规则有版 · 审核有痕</small></span>
      </button>
      <nav aria-label="主导航">
        <button :class="{ active: activePage === 'home' }" type="button" @click="activePage = 'home'">工作台</button>
        <button type="button">案件</button>
        <button type="button">阅卷</button>
        <button type="button">复核 <em>3</em></button>
      </nav>
      <button class="user" type="button" @click="activePage = 'settings'">林法官 · 设置</button>
    </header>

    <aside v-if="sidebarEnabled && activePage !== 'home'" class="sidebar" aria-label="工作区侧栏">
      <small>WORKSPACE</small>
      <button class="active" type="button">当前案件</button>
      <button type="button">材料与证据</button>
      <button type="button">量刑分析</button>
      <button type="button">人工复核</button>
      <p>首页保持无侧栏。侧栏仅作为个人工作偏好。</p>
    </aside>

    <main>
      <section v-if="activePage === 'home'" class="hero">
        <div class="hero-copy">
          <p class="eyebrow">LEXCYBER / SENTENCING DESK</p>
          <h1>让每一项量刑依据，<br><em>都能回到原文。</em></h1>
          <p class="lede">把案件事实、法条版本与人工裁量放进同一条可追溯链路。</p>
          <div class="hero-actions"><button class="primary" type="button">新建分析</button><button type="button">查看待复核 <span>3</span></button></div>
        </div>
        <div class="trace-card">
          <div class="trace-orbit"></div>
          <span class="node evidence">证据</span><span class="node rule">规则</span><span class="node human">人工</span>
          <strong>机器给出依据<br>人保留裁量</strong>
          <small>每一条建议都可定位到页码、段落和法源版本</small>
        </div>
      </section>

      <section class="content" :aria-label="pageTitle">
        <template v-if="activePage === 'home'">
          <div class="section-heading"><div><p class="eyebrow">OVERVIEW</p><h2>今天的工作节奏</h2></div><button type="button">全部案件 →</button></div>
          <div class="metric-grid"><article><small>进行中的案件</small><strong>08</strong><span class="good">↑ 2 本周</span></article><article><small>待人工复核</small><strong>03</strong><span class="warn">需要关注</span></article><article><small>依据回溯率</small><strong>96.8%</strong><span class="good">↑ 4.6%</span></article><article><small>平均处理时长</small><strong>12m</strong><span>较上周稳定</span></article></div>
          <div class="workspace-grid"><section class="panel cases"><div class="panel-heading"><h3>最近案件</h3><button type="button">筛选</button></div><div v-for="item in cases" :key="item.id" class="case-row"><span class="case-icon">LC</span><span><strong>{{ item.title }}</strong><small>{{ item.id }}</small></span><span class="status" :class="item.status === '待复核' ? 'review' : item.status === '分析中' ? 'running' : 'done'">{{ item.status }}</span><span class="progress"><i :style="{ width: `${item.progress}%` }"></i></span><span class="risk">{{ item.risk }}</span></div></section><section class="panel attention"><div class="panel-heading"><h3>需要关注</h3><span class="badge">3</span></div><p><b>一处法条版本待确认</b><small>危险驾驶罪 · 2015 版与现行版存在差异</small></p><p><b>一项事实缺少原文锚点</b><small>共同犯罪作用认定 · 第 4 页</small></p></section></div>
          <div class="flow-grid"><button type="button"><span>01</span><strong>材料归集</strong><small>PDF · DOCX · OCR</small></button><button type="button"><span>02</span><strong>事实抽取</strong><small>主体 · 时间线 · 证据</small></button><button type="button"><span>03</span><strong>规则比对</strong><small>法条版本 · 生效日期</small></button><button type="button"><span>04</span><strong>人工复核</strong><small>建议 · 留痕 · 版本</small></button></div>
        </template>

        <template v-else>
          <div class="section-heading"><div><p class="eyebrow">PREFERENCES</p><h2>用户设置</h2></div></div>
          <div class="settings-grid"><aside class="settings-nav"><button class="active" type="button">外观与布局</button><button type="button">通知偏好</button><button type="button">快捷键</button><p>首页固定无侧栏；这里仅配置内部工作区偏好。</p></aside><section class="panel settings-card"><h3>导航布局</h3><p>侧边栏只影响案件、阅卷、分析和复核页面。</p><div class="layout-options"><button :class="{ selected: !sidebarEnabled }" type="button" @click="sidebarEnabled = false"><strong>顶部导航</strong><small>更开阔，适合大多数用户</small></button><button :class="{ selected: sidebarEnabled }" type="button" @click="toggleSidebar"><strong>工作区侧栏</strong><small>仅在内部工作页显示</small></button></div><div class="palette"><span></span><span></span><span></span><span></span><b>极光衡链 · 深紫墨 / 极光紫 / 证据青 / 复核金</b></div></section></div>
        </template>
      </section>
    </main>
  </div>
</template>
