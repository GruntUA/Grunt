import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory('/app'),
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
      path: '/register',
      name: 'register',
      component: () => import('@/pages/auth/Register.vue'),
      meta: { public: true },
    },


    // Public app pages (no auth required)
    {
      path: '/public/:app/:page*',
      name: 'public-page',
      component: () => import('@/core/pages/PublicPage.vue'),
      meta: { public: true },
      props: true,
    },

    // Public Web Forms (no auth required)
    {
      path: '/form/:route',
      name: 'web-form',
      component: () => import('@/pages/public/PublicWebForm.vue'),
      meta: { public: true },
      props: true,
    },

    // Public Document Share (no auth required)
    {
      path: '/share/:token',
      name: 'document-share',
      component: () => import('@/pages/public/DocumentShareView.vue'),
      meta: { public: true },
      props: true,
    },

    // Desk (app launcher)
    {
      path: '/',
      name: 'desk',
      component: () => import('@/pages/DeskPage.vue'),
    },


    // Setup Wizard
    {
      path: '/setup',
      name: 'setup-wizard',
      component: () => import('@/pages/setup/SetupWizard.vue'),
      meta: { public: true },
    },
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
        // DocType builder — must come before generic :doctype/:id
        {
          path: 'DocType/:id',
          name: 'doctype-builder',
          component: () => import('@/pages/studio/builder/BuilderLayout.vue'),
          props: (route) => ({ doctype: route.params.id, workspaceName: route.params.workspaceName }),
        },
        {
          path: ':doctype/new',
          name: 'workspace-new',
          component: () => import('@/pages/workspace/WorkspaceFormView.vue'),
          props: (route) => ({
            workspaceName: route.params.workspaceName,
            doctype: route.params.doctype,
            id: null,
          }),
        },
        {
          path: ':doctype/:id',
          name: 'workspace-form',
          component: () => import('@/pages/workspace/WorkspaceFormView.vue'),
          props: true,
        },
        {
          path: ':doctype',
          name: 'workspace-list',
          component: () => import('@/pages/workspace/WorkspaceListView.vue'),
          props: true,
        },
        // Workspace Sidebar list (Studio → Воркспейси)
        {
          path: 'studio/workspaces',
          redirect: (route) => `/${route.params.workspaceName}/WorkspaceSidebar`,
        },
        // Backward compat: old /list/… URLs
        {
          path: 'list/:doctype',
          redirect: (route) => `/${route.params.workspaceName}/${route.params.doctype}`,
        },
        {
          path: 'list/:doctype/:id',
          redirect: (route) => `/${route.params.workspaceName}/${route.params.doctype}/${route.params.id}`,
        },
        {
          path: 'report/:reportName',
          name: 'workspace-report',
          component: () => import('@/pages/reports/ReportView.vue'),
          props: true,
        },
        {
          path: 'report-builder/:reportName?',
          name: 'report-builder',
          component: () => import('@/pages/reports/QueryReportBuilder.vue'),
          props: true,
        },
        {
          path: 'dashboard/:dashboardName',
          name: 'workspace-dashboard',
          component: () => import('@/pages/workspace/WorkspaceDashboard.vue'),
          props: true,
        },
        {
          path: 'search',
          name: 'workspace-search',
          component: () => import('@/pages/workspace/SearchResultsPage.vue'),
          props: true,
        },
        {
          path: 'files',
          name: 'file-manager',
          component: () => import('@/pages/desk/FileManager.vue'),
          props: true,
        },
        // Legacy admin routes — redirect to standard DocType ListViews
        {
          path: 'rbac',
          redirect: (route) => `/${route.params.workspaceName}/DocTypePermission`,
        },
        {
          path: 'hooks',
          name: 'hook-manager',
          component: () => import('@/pages/admin/HookManager.vue'),
          props: true,
        },
        {
          path: 'activity-log',
          redirect: (route) => `/${route.params.workspaceName}/ActivityLog`,
        },
        {
          path: 'email-settings',
          redirect: (route) => `/${route.params.workspaceName}/EmailAccount`,
        },
        {
          path: 'settings',
          redirect: (route) => `/${route.params.workspaceName}/SystemSettings/SystemSettings`,
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
