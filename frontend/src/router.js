import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/setup', name: 'setup', component: () => import('./views/SetupView.vue') },
    { path: '/', name: 'library', component: () => import('./views/LibraryView.vue') },
    { path: '/search', name: 'search', component: () => import('./views/SearchView.vue') },
    { path: '/bangumi/:id', name: 'bangumi', component: () => import('./views/BangumiDetailView.vue') },
    { path: '/calendar', name: 'calendar', component: () => import('./views/CalendarView.vue') },
    { path: '/bd', name: 'bd', component: () => import('./views/BdLibraryView.vue') },
    { path: '/subscriptions', name: 'subscriptions', component: () => import('./views/SubscriptionsView.vue') },
    { path: '/downloads', name: 'downloads', component: () => import('./views/DownloadsView.vue') },
    { path: '/logs', name: 'logs', component: () => import('./views/LogView.vue') },
    { path: '/settings', name: 'settings', component: () => import('./views/SettingsView.vue') },
  ],
})

// 首次配置守卫:未配置(setup_done 假且无番剧数据)→ 强制进 /setup;已配置访问 /setup → 回主页。
let _configured = null   // null=未知,true/false=已知(避免每次导航都查)
router.beforeEach(async (to) => {
  if (_configured === null) {
    try {
      const r = await fetch('/api/setup/status')
      _configured = (await r.json()).configured
    } catch {
      _configured = true   // 接口异常不锁死用户
    }
  }
  if (!_configured && to.name !== 'setup') return { name: 'setup' }
  if (_configured && to.name === 'setup') return { name: 'library' }
  return true
})

export default router
