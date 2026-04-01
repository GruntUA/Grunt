import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    // Auth
    {
      path: '/login',
      name: 'login',
      component: () => import('@/pages/auth/Login.vue'),
      meta: { public: true },
    },
    {
      path: '/forgot-password',
      name: 'forgot-password',
      component: () => import('@/pages/auth/ForgotPassword.vue'),
      meta: { public: true },
    },
    {
      path: '/reset-password',
      name: 'reset-password',
      component: () => import('@/pages/auth/ResetPassword.vue'),
      meta: { public: true },
    },
    {
      path: '/mfa-verify',
      name: 'mfa-verify',
      component: () => import('@/pages/auth/MfaVerify.vue'),
      meta: { public: true },
    },
    {
      path: '/mfa-setup',
      name: 'mfa-setup',
      component: () => import('@/pages/auth/MfaSetup.vue'),
    },

    // Public app pages (no auth required)
    {
      path: '/public/:app/:page*',
      name: 'public-page',
      component: () => import('@/core/pages/PublicPage.vue'),
      meta: { public: true },
      props: true,
    },

    // Desk (app launcher)
    {
      path: '/',
      name: 'desk',
      component: () => import('@/pages/DeskPage.vue'),
    },

    // App Workspace (dynamic /:workspaceName)
    {
      path: '/:workspaceName',
      component: () => import('@/pages/workspace/WorkspaceLayout.vue'),
      props: true,
      children: [
        {
          path: '',
          name: 'workspace-home',
          component: () => import('@/pages/workspace/WorkspaceHome.vue'),
          props: true,
        },
        {
          path: 'list/:doctype',
          name: 'workspace-list',
          component: () => import('@/pages/workspace/WorkspaceListView.vue'),
          props: true,
        },
        {
          path: 'list/:doctype/new',
          name: 'workspace-new',
          component: () => import('@/pages/workspace/WorkspaceFormView.vue'),
          props: (route) => ({
            workspaceName: route.params.workspaceName,
            doctype: route.params.doctype,
            id: null,
          }),
        },
        // DocType builder — must come before the generic list/:doctype/:id route
        {
          path: 'list/DocType/:id',
          name: 'doctype-builder',
          component: () => import('@/pages/studio/builder/BuilderLayout.vue'),
          props: (route) => ({ doctype: route.params.id, workspaceName: route.params.workspaceName }),
        },
        {
          path: 'list/:doctype/:id',
          name: 'workspace-form',
          component: () => import('@/pages/workspace/WorkspaceFormView.vue'),
          props: true,
        },
        {
          path: 'report/:reportName',
          name: 'workspace-report',
          component: () => import('@/pages/workspace/WorkspaceReportView.vue'),
          props: true,
        },
        {
          path: 'dashboard/:dashboardName',
          name: 'workspace-dashboard',
          component: () => import('@/pages/workspace/WorkspaceDashboard.vue'),
          props: true,
        },
        {
          path: 'data-import/:id?',
          name: 'data-import',
          component: () => import('@/pages/desk/DataImport/DataImportPage.vue'),
          props: true,
        },
      ],
    },
    // 403 forbidden
    {
      path: '/403',
      name: 'forbidden',
      component: () => import('@/pages/errors/Forbidden.vue'),
      meta: { public: true },
    },
    // 404 catch-all
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('@/pages/errors/NotFound.vue'),
      meta: { public: true },
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
