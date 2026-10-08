import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: {
    port: 5173,
    proxy: {
      // 后端走 Docker 栈时，宿主机只对外暴露 nginx 的 18080（Java 的 8080 仅在容器内网）。
      // X-Reviewer-Id 复刻 nginx 的 trusted-header 审核身份，否则审核 approve/reject 会报错。
      '/v1': {
        target: 'http://127.0.0.1:18080',
        changeOrigin: true,
        headers: { 'X-Reviewer-Id': 'local-reviewer' },
      },
      '/v2': {
        target: 'http://127.0.0.1:18080',
        changeOrigin: true,
        headers: { 'X-Reviewer-Id': 'local-reviewer' },
      },
    },
  },
})
