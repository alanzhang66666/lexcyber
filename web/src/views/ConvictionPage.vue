<script setup lang="ts">
import PlaceholderBanner from '../components/PlaceholderBanner.vue'
</script>

<template>
  <div class="page-stack">
    <PlaceholderBanner />
    <header class="page-heading">
      <div>
        <p class="eyebrow">定罪研判</p>
        <h1>定罪研判</h1>
        <p>解析行为要素，输出主观罪过四层识别、法域冲突研判与定罪结论。当前为静态版式样例，字段待 T3 业务输出确定后接入。</p>
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
            <span>或直接输入案情描述</span>
            <textarea rows="4" disabled placeholder="示例：境外主体通过即时通讯实施电信网络诈骗…" />
          </label>
          <RouterLink class="button button-quiet" to="/cases">导入案件材料</RouterLink>
        </form>
      </article>
      <article class="panel">
        <div class="panel-heading"><div><p class="section-index">02</p><h2>行为要素</h2></div></div>
        <dl class="data-list">
          <div><dt>行为地 / 结果地</dt><dd class="placeholder-text">待解析</dd></div>
          <div><dt>主体国籍</dt><dd class="placeholder-text">待解析</dd></div>
          <div><dt>数据跨境流向</dt><dd class="placeholder-text">待解析</dd></div>
          <div><dt>境外关联方</dt><dd class="placeholder-text">待解析</dd></div>
          <div><dt>行为模式标签</dt><dd class="placeholder-text">待解析</dd></div>
          <div><dt>时间线</dt><dd class="placeholder-text">待解析</dd></div>
        </dl>
      </article>
    </section>

    <section class="panel">
      <div class="panel-heading"><div><p class="section-index">03</p><h2>主观罪过四层识别</h2></div></div>
      <div class="metric-grid">
        <article class="metric-card"><span>明确明知</span><strong class="placeholder-text">待判断</strong></article>
        <article class="metric-card"><span>推定明知</span><strong class="placeholder-text">待判断</strong></article>
        <article class="metric-card"><span>过失涉罪</span><strong class="placeholder-text">待判断</strong></article>
        <article class="metric-card"><span>无过错合规</span><strong class="placeholder-text">待判断</strong></article>
      </div>
      <p class="panel-note">展示四级判断结果及依据，标注事实支撑与待核实事项；合规筛查结论将作为判断依据之一。</p>
    </section>

    <section class="panel">
      <div class="panel-heading"><div><p class="section-index">04</p><h2>法域冲突研判</h2></div></div>
      <dl class="data-list">
        <div><dt>管辖识别</dt><dd class="placeholder-text">待接入</dd></div>
        <div><dt>中外罪名对照</dt><dd class="placeholder-text">待接入</dd></div>
        <div><dt>法律光谱定位</dt><dd class="placeholder-text">民事 / 行政 / 刑事边界 —— 待接入</dd></div>
        <div><dt>双重追责风险</dt><dd class="placeholder-text">待接入</dd></div>
      </dl>
    </section>

    <section class="panel">
      <div class="panel-heading"><div><p class="section-index">05</p><h2>定罪结论输出</h2></div></div>
      <dl class="data-list">
        <div><dt>罪名锚定</dt><dd class="placeholder-text">待接入</dd></div>
        <div><dt>定罪依据</dt><dd class="placeholder-text">待接入</dd></div>
      </dl>
      <p class="panel-note">支持人工修正全部研判结论。</p>
    </section>
  </div>
</template>

<style scoped>
.placeholder-text { color: var(--lc-muted); }
</style>
