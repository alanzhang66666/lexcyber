<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'
</script>

<template>
  <div class="app-shell">
    <a class="skip-link" href="#main-content">跳到主要内容</a>
    <header class="topbar">
      <RouterLink class="brand" to="/tasks" aria-label="LexCyber 网域衡鉴首页">
        <span class="brand-mark" aria-hidden="true"><i></i><b>衡</b></span>
        <span class="brand-copy">
          <strong>LexCyber <em>网域衡鉴</em></strong>
          <small>涉外互联网犯罪刑事合规与量刑辅助系统</small>
        </span>
      </RouterLink>
      <nav class="primary-nav" aria-label="主要导航">
        <RouterLink to="/tasks"><span aria-hidden="true">▦</span>任务中心</RouterLink>
        <RouterLink to="/reviews"><span aria-hidden="true">◇</span>人工复核</RouterLink>
      </nav>
      <div class="environment" title="当前连接本地开发服务">
        <span aria-hidden="true"></span>
        <div><small>运行环境</small><strong>LOCAL</strong></div>
      </div>
    </header>
    <main id="main-content" class="main-content" tabindex="-1">
      <RouterView />
    </main>
    <footer class="app-footer">
      <span>LexCyber 网域衡鉴 · Execution Contract v0.3</span>
      <span>辅助研判，不自动替代司法裁量</span>
    </footer>
  </div>
</template>
