import { createRouter, createWebHistory, type RouteLocationNormalized } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { loadSiteConfig } from '@/core/composables/useSiteConfig'
import { setPageTitle } from '@/core/composables/usePageTitle'
import { i18n } from '@/plugins/i18n'

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
        {
          // `:id` == "new" is the create sentinel (matches the rest of the app —
          // scripting executor, useLinkCreate — which all treat "new" this way);
          // map it to a null id so DocTypeForm renders a blank form.
          path: ':doctype/:id(.*)',
          name: 'workspace-form',
          component: () => import('@/pages/app/AppFormView.vue'),
          props: (route) => ({
            workspaceName: route.params.workspaceName,
            doctype: route.params.doctype,
            id: route.params.id === 'new' ? null : route.params.id,
          }),
        },
        {
          path: ':doctype',
          name: 'workspace-list',
          component: () => import('@/pages/app/AppListView.vue'),
          props: true,
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

/**
 * Param-derived default tab title, applied on every navigation. Pages that load
 * richer data (a document title, a DocType/Page/Report label) refine this by
 * calling `setPageTitle()` after their data resolves.
 */
function routeTitle(to: RouteLocationNormalized): string {
  const t = i18n.global.t
  // Route params can be `string | string[]` (repeatable segments) — flatten.
  const s = (v: unknown): string => (Array.isArray(v) ? v.join('/') : String(v ?? ''))
  const p = to.params
  const q = to.query as Record<string, unknown>
  switch (to.name) {
    case 'login': return t('Sign in')
    case 'register': return t('Sign up')
    case 'forgot-password': return t('Reset password')
    case 'reset-password': return t('Reset password')
    case 'mfa-verify': return t('Two-factor authentication')
    case 'setup-wizard': return t('Setup')
    case 'desk': return t('Home')
    case 'forbidden': return t('Access denied')
    case 'not-found': return t('Page not found')
    case 'file-manager': return t('Files')
    case 'workspace-search': {
      const term = String(q.q ?? '').trim()
      return term ? `${t('Search')}: ${term}` : t('Search')
    }
    case 'workspace-home': return s(p.workspaceName)
    case 'workspace-form':
      return !p.id || p.id === 'new' ? `${t('New')} ${s(p.doctype)}`.trim() : s(p.id)
    case 'workspace-list': return s(p.doctype)
    case 'workspace-page': return s(p.pageName)
    case 'workspace-report':
    case 'report-builder': return s(p.reportName)
    default: return ''
  }
}

router.afterEach((to) => {
  setPageTitle(routeTitle(to))
})

export default router
