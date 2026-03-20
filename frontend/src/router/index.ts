import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/pages/auth/Login.vue'),
      meta: { public: true },
    },
    {
      path: '/studio',
      component: () => import('@/pages/desk/DeskLayout.vue'),
      children: [
        {
          path: '',
          name: 'studio',
          component: () => import('@/pages/studio/DocTypeList.vue'),
        },
        {
          path: 'users',
          name: 'studio-users',
          component: () => import('@/pages/studio/roles/UsersPage.vue'),
        },
        {
          path: 'roles',
          name: 'studio-roles',
          component: () => import('@/pages/studio/roles/RolesPage.vue'),
        },
        {
          path: ':doctype/builder',
          name: 'builder',
          component: () => import('@/pages/studio/builder/BuilderLayout.vue'),
          props: true,
        },
        {
          path: ':doctype/workflow',
          name: 'workflow-editor',
          component: () => import('@/pages/studio/workflow/WorkflowEditor.vue'),
          props: true,
        },
      ],
    },
    {
      path: '/',
      component: () => import('@/pages/desk/DeskLayout.vue'),
      children: [
        {
          path: '',
          name: 'home',
          component: () => import('@/pages/desk/DeskHome.vue'),
        },
        {
          path: 'reports',
          name: 'reports',
          component: () => import('@/pages/desk/reports/ReportList.vue'),
        },
        {
          path: 'reports/:name',
          name: 'report-view',
          component: () => import('@/pages/desk/reports/ReportView.vue'),
          props: true,
        },
        {
          path: ':doctype',
          name: 'list',
          component: () => import('@/pages/desk/DocTypeList.vue'),
          props: true,
        },
        {
          path: ':doctype/new',
          name: 'create',
          component: () => import('@/pages/desk/DocTypeForm.vue'),
          props: (route) => ({ doctype: route.params.doctype, id: null }),
        },
        {
          path: ':doctype/:id',
          name: 'form',
          component: () => import('@/pages/desk/DocTypeForm.vue'),
          props: true,
        },
      ],
    },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (to.meta.public) return true
  if (!auth.isLoggedIn) return { name: 'login' }
  if (!auth.user) await auth.fetchMe()
  return true
})

export default router
