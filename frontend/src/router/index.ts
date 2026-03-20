import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { resolvePageComponent } from '@/core/pages/registry'
import type { AppPage } from '@/core/api/pages'

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
      name: 'desk',
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

// ── Dynamic app pages ───────────────────────────────────────────────────
let pagesLoaded = false

async function loadAppPages(): Promise<void> {
  if (pagesLoaded) return
  pagesLoaded = true

  try {
    const { fetchPages } = await import('@/core/api/pages')
    const pages: AppPage[] = await fetchPages()

    for (const page of pages) {
      const loader = resolvePageComponent(page.component)
      if (!loader) continue

      const routePath = page.route.startsWith('/') ? page.route.slice(1) : page.route
      router.addRoute('desk', {
        path: routePath,
        name: `app-page-${page.route}`,
        component: loader as () => Promise<{ default: unknown }>,
        meta: { appPage: true, pageTitle: page.title },
      })
    }

    // Check if any page is_default_home — redirect '/' to it
    const defaultPage = pages.find((p) => p.is_default_home)
    if (defaultPage) {
      router.addRoute('desk', {
        path: '',
        name: 'home',
        redirect: defaultPage.route,
      })
    }
  } catch {
    // Pages are optional — app works without them
  }
}

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (to.meta.public) return true
  if (!auth.isLoggedIn) return { name: 'login' }
  if (!auth.user) await auth.fetchMe()

  // Load dynamic pages once after auth
  if (!pagesLoaded) {
    await loadAppPages()
    // Re-resolve the current route with new dynamic routes
    return to.fullPath
  }

  return true
})

export default router
