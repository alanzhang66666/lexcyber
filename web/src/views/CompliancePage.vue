<script setup lang="ts">
import PlaceholderBanner from '../components/PlaceholderBanner.vue'
</script>

<template>
  <div class="page-stack">
    <PlaceholderBanner />
    <header class="page-heading">
      <div>
        <p class="eyebrow">合规筛查</p>
        <h1>合规筛查</h1>
        <p>上传跨境业务与企业合规材料，体检风险并生成整改建议。当前为静态版式样例，字段待 T3 业务输出确定后接入。</p>
      </div>
      <span class="subtle-chip">开发中 · 版式样例</span>
    </header>

    <section class="work-grid">
      <article class="panel">
        <div class="panel-heading"><div><p class="section-index">01</p><h2>材料上传与要素解析</h2></div></div>
        <form class="form-stack" @submit.prevent>
          <label>
            <span>上传材料</span>
            <input type="file" disabled />
          </label>
          <label>
            <span>或直接输入业务描述</span>
            <textarea rows="4" disabled placeholder="示例：境外电商平台面向境内用户提供跨境支付服务…" />
          </label>
          <RouterLink class="button button-quiet" to="/cases">导入案件材料</RouterLink>
        </form>
      </article>
      <article class="panel">
        <div class="panel-heading"><div><p class="section-index">02</p><h2>业务行为要素</h2></div></div>
        <dl class="data-list">
          <div><dt>业务类型</dt><dd class="placeholder-text">待解析</dd></div>
          <div><dt>数据流动路径</dt><dd class="placeholder-text">待解析</dd></div>
          <div><dt>资金流转轨迹</dt><dd class="placeholder-text">待解析</dd></div>
          <div><dt>用户所在地域</dt><dd class="placeholder-text">待解析</dd></div>
          <div><dt>服务提供方式</dt><dd class="placeholder-text">待解析</dd></div>
        </dl>
      </article>
    </section>

    <section class="panel">
      <div class="panel-heading"><div><p class="section-index">03</p><h2>合规体检报告</h2></div></div>
      <div class="metric-grid">
        <article class="metric-card"><span>风险等级</span><strong class="placeholder-text">待评估</strong></article>
        <article class="metric-card"><span>纸面合规判定</span><strong class="placeholder-text">待评估</strong></article>
        <article class="metric-card"><span>境外关联预判</span><strong class="placeholder-text">待评估</strong></article>
        <article class="metric-card"><span>反向风险扫描</span><strong class="placeholder-text">待评估</strong></article>
      </div>
      <dl class="data-list">
        <div><dt>犯罪风险对应性</dt><dd class="placeholder-text">制度覆盖罪名 / 业务 / 地域 / 行为模式 —— 待接入</dd></div>
        <div><dt>境外关联三级预判</dt><dd class="placeholder-text">形式独立 / 实质关联待查 / 实质控制 —— 待接入</dd></div>
        <div><dt>制度建立与案发时间</dt><dd class="placeholder-text">时间证据链 —— 待接入</dd></div>
      </dl>
    </section>

    <section class="panel">
      <div class="panel-heading"><div><p class="section-index">04</p><h2>合规整改建议清单</h2></div></div>
      <p class="panel-note">逐条输出风险点、踩线临界点、优先整改项与整改建议，支持人工修改并记录轨迹。</p>
      <div class="empty-state">
        <strong>暂无整改建议</strong>
        <p>完成合规体检后生成。</p>
      </div>
    </section>
  </div>
</template>

<style scoped>
.placeholder-text { color: var(--lc-muted); }
</style>
