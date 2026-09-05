import { createRouter, createWebHistory } from 'vue-router'
import { lastCaseId } from './data/placeholder-cases'
import { isAuthenticated } from './lib/auth'
import AnalysisPage from './views/AnalysisPage.vue'
import AuditPage from './views/AuditPage.vue'
import AuthPage from './views/AuthPage.vue'
import CaseNewPage from './views/CaseNewPage.vue'
import CasesPage from './views/CasesPage.vue'
import CaseWorkspacePage from './views/CaseWorkspacePage.vue'
import DocketPage from './views/DocketPage.vue'
import HomePage from './views/HomePage.vue'
import ReviewDetailPage from './views/ReviewDetailPage.vue'
import ReviewsPage from './views/ReviewsPage.vue'
import RulesPage from './views/RulesPage.vue'
import SettingsPage from './views/SettingsPage.vue'
import SourcesPage from './views/SourcesPage.vue'
import TaskDetailPage from './views/TaskDetailPage.vue'
import TasksPage from './views/TasksPage.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: AuthPage, meta: { title: '登录', public: true } },
    { path: '/', name: 'home', component: HomePage, meta: { title: '首页', public: true } },
    { path: '/cases', name: 'cases', component: CasesPage, meta: { title: '案件中心' } },
    { path: '/cases/new', name: 'case-new', component: CaseNewPage, meta: { title: '新建案件' } },
    { path: '/cases/:caseId', name: 'case-workspace', component: CaseWorkspacePage, props: true, meta: { title: '案件工作区' } },
    { path: '/cases/:caseId/docket', name: 'docket', component: DocketPage, props: true, meta: { title: '智能阅卷' } },
    { path: '/cases/:caseId/analysis', name: 'analysis', component: AnalysisPage, props: true, meta: { title: '量刑分析' } },
    { path: '/docket', redirect: () => `/cases/${lastCaseId()}/docket` },
    { path: '/analysis', redirect: () => `/cases/${lastCaseId()}/analysis` },
    { path: '/sources', name: 'sources', component: SourcesPage, meta: { title: '法源与类案' } },
    { path: '/rules', name: 'rules', component: RulesPage, meta: { title: '量刑规则' } },
    { path: '/audit', name: 'audit', component: AuditPage, meta: { title: '统计与审计' } },
    { path: '/settings', name: 'settings', component: SettingsPage, meta: { title: '用户设置' } },
    { path: '/tasks', name: 'tasks', component: TasksPage, meta: { title: '执行任务' } },
    { path: '/tasks/:taskId', name: 'task-detail', component: TaskDetailPage, props: true, meta: { title: '任务详情' } },
    { path: '/reviews', name: 'reviews', component: ReviewsPage, meta: { title: '人工复核' } },
    { path: '/reviews/:reviewId', name: 'review-detail', component: ReviewDetailPage, props: true, meta: { title: '复核详情' } },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach((to) => {
  const signedIn = isAuthenticated()
  if (!signedIn && to.meta.public !== true) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (signedIn && to.name === 'login') {
    return { path: '/' }
  }
  return true
})

router.afterEach((to) => {
  const page = typeof to.meta.title === 'string' ? to.meta.title : '工作台'
  document.title = `${page} · LexCyber 网域衡鉴`
})

export default router
