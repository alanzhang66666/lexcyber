import { createRouter, createWebHistory } from 'vue-router'
import ReviewDetailPage from './views/ReviewDetailPage.vue'
import ReviewsPage from './views/ReviewsPage.vue'
import TaskDetailPage from './views/TaskDetailPage.vue'
import TasksPage from './views/TasksPage.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/tasks' },
    { path: '/tasks', name: 'tasks', component: TasksPage },
    { path: '/tasks/:taskId', name: 'task-detail', component: TaskDetailPage, props: true },
    { path: '/reviews', name: 'reviews', component: ReviewsPage },
    { path: '/reviews/:reviewId', name: 'review-detail', component: ReviewDetailPage, props: true },
    { path: '/:pathMatch(.*)*', redirect: '/tasks' },
  ],
  scrollBehavior: () => ({ top: 0 }),
})

export default router
