<script setup lang="ts">
import { computed, onMounted } from 'vue'
import logoUrl from '../assets/logo.png'
import { CORE_MODULES, modulePath } from '../data/modules'
import { currentCaseId, resolveT1CaseId } from '../lib/current-case'

const features = computed(() => CORE_MODULES.map((module) => ({ ...module, to: modulePath(module, currentCaseId.value) })))

onMounted(() => {
  void resolveT1CaseId()
})
</script>

<template>
  <div class="home-landing">
    <section class="home-hero">
      <div class="home-hero-copy">
        <p class="home-product">涉外互联网犯罪刑事合规与量刑辅助系统</p>
        <h1>Let Every Trace<br>Return to Source.</h1>
        <p class="home-lead">
          穿透数据迷雾，锚定资金踪迹。<br>
          规则可核，过程可溯。<br>
          让智能辅助研判，让裁量归于人心。
        </p>
        <div class="home-cta">
          <RouterLink class="home-btn home-btn-primary" to="/cases">立即体验 →</RouterLink>
          <a class="home-btn home-btn-ghost" href="#home-functions">查看功能</a>
        </div>
        <ul class="home-trust">
          <li>
            <span aria-hidden="true">⛨</span>
            证据有源可追溯
          </li>
          <li>
            <span aria-hidden="true">⚡</span>
            规则版本可核验
          </li>
          <li>
            <span aria-hidden="true">◇</span>
            审核决定有留痕
          </li>
        </ul>
      </div>

      <div class="home-hero-art" aria-hidden="true">
        <svg class="home-deco home-deco-dots" viewBox="0 0 120 220" fill="none">
          <g fill="#7554f6" fill-opacity=".22">
            <circle cx="18" cy="20" r="3" /><circle cx="42" cy="36" r="2.5" /><circle cx="22" cy="58" r="2" />
            <circle cx="48" cy="78" r="3" /><circle cx="16" cy="96" r="2.2" /><circle cx="40" cy="118" r="2.6" />
            <circle cx="24" cy="142" r="3" /><circle cx="50" cy="166" r="2" /><circle cx="18" cy="188" r="2.4" />
          </g>
        </svg>
        <div class="home-trace-scene">
          <svg class="home-trace-links" viewBox="0 0 440 360" fill="none">
            <ellipse class="home-ring home-ring-outer" cx="220" cy="176" rx="92" ry="92" stroke="#7554f6" stroke-width="1.2" />
            <ellipse class="home-ring home-ring-inner" cx="220" cy="176" rx="58" ry="58" stroke="#7554f6" stroke-width="1.2" />
            <ellipse class="home-ring home-ring-pulse" cx="220" cy="176" rx="40" ry="40" stroke="#7554f6" stroke-width="1" />
            <path d="M128 176h184M220 84v184" stroke="#7554f6" stroke-opacity=".12" stroke-width="1" />
            <circle class="home-node" cx="168" cy="132" r="4" fill="#7554f6" />
            <circle class="home-node" cx="274" cy="124" r="3" fill="#7554f6" />
            <circle class="home-node" cx="286" cy="208" r="4" fill="#7554f6" />
            <circle class="home-node" cx="154" cy="214" r="3" fill="#7554f6" />
            <path class="home-trace-base" d="M118 92C150 128 176 148 220 176" />
            <path class="home-trace-base" d="M322 70C286 110 252 146 220 176" />
            <path class="home-trace-base" d="M318 292C278 250 248 210 220 176" />
            <path class="home-trace-flow" d="M118 92C150 128 176 148 220 176" />
            <path class="home-trace-flow home-trace-flow-b" d="M322 70C286 110 252 146 220 176" />
            <path class="home-trace-flow home-trace-flow-c" d="M318 292C278 250 248 210 220 176" />
            <circle class="home-spark" r="3.4" fill="#7554f6">
              <animate attributeName="opacity" values="0;1;1;0" keyTimes="0;0.12;0.78;1" dur="3.2s" repeatCount="indefinite" />
              <animateMotion dur="3.2s" repeatCount="indefinite" path="M118 92C150 128 176 148 220 176" />
            </circle>
            <circle class="home-spark" r="3.4" fill="#7554f6">
              <animate attributeName="opacity" values="0;1;1;0" keyTimes="0;0.12;0.78;1" dur="3.4s" begin="-1.1s" repeatCount="indefinite" />
              <animateMotion dur="3.4s" begin="-1.1s" repeatCount="indefinite" path="M322 70C286 110 252 146 220 176" />
            </circle>
            <circle class="home-spark" r="3.4" fill="#7554f6">
              <animate attributeName="opacity" values="0;1;1;0" keyTimes="0;0.12;0.78;1" dur="3.6s" begin="-2.2s" repeatCount="indefinite" />
              <animateMotion dur="3.6s" begin="-2.2s" repeatCount="indefinite" path="M318 292C278 250 248 210 220 176" />
            </circle>
          </svg>
          <article class="home-float home-float-source">
            <span>原</span>
            <div>
              <small>证据有源</small>
              <strong>事实回到原文</strong>
            </div>
          </article>
          <article class="home-float home-float-rule">
            <span>规</span>
            <div>
              <small>规则有版</small>
              <strong>条文可以核验</strong>
            </div>
          </article>
          <div class="home-float-hub">
            <img :src="logoUrl" alt="" />
          </div>
          <article class="home-float home-float-review">
            <span>人</span>
            <div>
              <small>审核有痕</small>
              <strong>裁量留在人手</strong>
            </div>
          </article>
        </div>
      </div>
    </section>

    <section id="home-functions" class="home-functions">
      <RouterLink v-for="item in features" :key="item.key" class="home-feature" :to="item.to">
        <span class="home-feature-icon" :data-icon="item.icon" aria-hidden="true">
          <svg v-if="item.icon === 'conviction'" viewBox="0 0 32 32" fill="none">
            <circle cx="8" cy="10" r="3" stroke="currentColor" stroke-width="1.6" />
            <circle cx="24" cy="8" r="3" stroke="currentColor" stroke-width="1.6" />
            <circle cx="18" cy="22" r="3" stroke="currentColor" stroke-width="1.6" />
            <path d="M11 11.5 15.5 20M21.5 10.2 19.6 19" stroke="currentColor" stroke-width="1.6" />
          </svg>
          <svg v-else-if="item.icon === 'compliance'" viewBox="0 0 32 32" fill="none">
            <path d="M7 16h12" stroke="currentColor" stroke-width="1.6" />
            <path d="M16 11h9v10h-9" stroke="currentColor" stroke-width="1.6" />
            <path d="M7 16c0-5 3-8 8-8M7 16c0 5 3 8 8 8" stroke="currentColor" stroke-width="1.6" />
            <path d="M21 16h5l-3-3M26 16l-3 3" stroke="currentColor" stroke-width="1.6" />
          </svg>
          <svg v-else-if="item.icon === 'sentencing'" viewBox="0 0 32 32" fill="none">
            <path d="M8 24V12M16 24V8M24 24v-8" stroke="currentColor" stroke-width="1.6" />
            <path d="M6 24h20" stroke="currentColor" stroke-width="1.6" />
          </svg>
          <svg v-else viewBox="0 0 32 32" fill="none">
            <rect x="8" y="6" width="16" height="20" rx="2" stroke="currentColor" stroke-width="1.6" />
            <path d="M12 12h8M12 16h8M12 20h5" stroke="currentColor" stroke-width="1.6" />
          </svg>
        </span>
        <h2>{{ item.title }}</h2>
        <p>{{ item.desc }}</p>
        <span class="home-feature-enter">进入 →</span>
      </RouterLink>
    </section>
  </div>
</template>
