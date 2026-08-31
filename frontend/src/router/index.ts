import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { loadSiteConfig, siteConfigState } from '@/core/composables/useSiteConfig'

const router = createRouter({
  history: createWebHistory('/'),
  routes: [
    // Auth
    {
      path: '/login',
      name: 'login',
      component: () => import('@/pages/auth/Login.vue'),
      meta: { public: true },
    },
    {
      // Same combined component as /login — it switches to the sign-up form
      // based on the path.
      path: '/signup',
      name: 'register',
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
      path: '/app',
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
      path: '/app/:workspaceName',
      alias: '/:workspaceName',
      component: () => import('@/pages/app/AppLayout.vue'),
      props: true,
      children: [
        {
          path: '',
          name: 'workspace-home',
          component: () => import('@/pages/app/AppHome.vue'),
          props: true,
        },
        // Backward compatibility: old DocType studio route now points to standard DocType form.
        {
          path: 'studio/DocType/:id',
          redirect: (route) => `/${route.params.workspaceName}/DocType/${route.params.id}`,
        },
        {
          path: ':doctype/new',
          name: 'workspace-new',
          component: () => import('@/pages/app/AppFormView.vue'),
          props: (route) => ({
            workspaceName: route.params.workspaceName,
            doctype: route.params.doctype,
            id: null,
          }),
        },
        {
          path: ':doctype/:id(.*)',
          name: 'workspace-form',
          component: () => import('@/pages/app/AppFormView.vue'),
          props: true,
        },
        {
          path: ':doctype',
          name: 'workspace-list',
          component: () => import('@/pages/app/AppListView.vue'),
          props: true,
        },
        // AppMenu list (Studio → Меню додатків)
        {
          path: 'studio/workspaces',
          redirect: (route) => `/app/${route.params.workspaceName}/AppMenu`,
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
          sensitive: true,
          component: () => import('@/pages/reports/ReportView.vue'),
          props: true,
        },
        {
          path: 'report-builder/:reportName?',
          name: 'report-builder',
          sensitive: true,
          component: () => import('@/pages/reports/QueryReportBuilder.vue'),
          props: true,
        },
        {
          path: 'page/:pageName',
          name: 'workspace-page',
          sensitive: true,
          component: () => import('@/pages/app/AppPage.vue'),
          props: true,
        },
        {
          path: 'search',
          name: 'workspace-search',
          component: () => import('@/pages/app/SearchResultsPage.vue'),
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
          path: 'hooks',
          redirect: (route) => `/${route.params.workspaceName}/Hook`,
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
  // Branding / locale / date-format config must be ready before the first paint.
  await loadSiteConfig()

  // Redirect alias paths (/:workspaceName/...) to canonical /app/:workspaceName/...
  // When matched via alias, matched[0].path is the alias path (e.g. /:workspaceName),
  // but matched[0].aliasOf?.path is the canonical path (/app/:workspaceName).
  const firstRecord = to.matched[0]
  const isWorkspaceRoute =
    firstRecord?.path === '/app/:workspaceName' ||
    (firstRecord as any)?.aliasOf?.path === '/app/:workspaceName'
  if (isWorkspaceRoute && !to.path.startsWith('/app/')) {
    return '/app' + to.path
  }

  const auth = useAuthStore()

  // Already-authenticated visitor hits the login page directly (e.g. via a
  // bookmark or /login link) — send them straight to the desk instead of
  // showing the form again. isLoggedIn only checks token presence; fetchMe
  // confirms the token is still valid server-side (and clears it on 401/403).
  if ((to.name === 'login' || to.name === 'register') && auth.isLoggedIn) {
    if (!auth.user) await auth.fetchMe()
    if (auth.isLoggedIn) return { name: 'desk' }
  }

  if (to.meta.public) return true
  if (!auth.isLoggedIn) return { name: 'login' }
  if (!auth.user) await auth.fetchMe()
  return true
})

router.afterEach(() => {
  document.title = siteConfigState().appName || 'Ґрунт'
})

export default router
