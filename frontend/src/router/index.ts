import { createRouter, createWebHistory } from 'vue-router'
import DefaultLayout from '@/layouts/DefaultLayout.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: DefaultLayout,
      redirect: '/dashboard',
      children: [
        {
          path: 'dashboard',
          name: 'Dashboard',
          component: () => import('@/views/Dashboard.vue'),
          meta: { title: '仪表盘' },
        },
        {
          path: 'market',
          name: 'Market',
          component: () => import('@/views/Market.vue'),
          meta: { title: '行情' },
        },
        {
          path: 'strategy',
          name: 'Strategy',
          component: () => import('@/views/Strategy.vue'),
          meta: { title: '策略' },
        },
        {
          path: 'portfolio',
          name: 'Portfolio',
          component: () => import('@/views/Portfolio.vue'),
          meta: { title: '组合' },
        },
        {
          path: 'analysis',
          name: 'Analysis',
          component: () => import('@/views/Analysis.vue'),
          meta: { title: '分析' },
        },
        {
          path: 'factors',
          name: 'Factors',
          component: () => import('@/views/Factors.vue'),
          meta: { title: '因子库' },
        },
      ],
    },
  ],
})

export default router
