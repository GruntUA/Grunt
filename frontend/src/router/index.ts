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

    // Desk (app launcher)
    {
      path: '/',
      name: 'desk',
      component: () => import('@/pages/DeskPage.vue'),
    },

    // Studio
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
          path: 'workspaces',
          name: 'studio-workspaces',
          component: () => import('@/pages/studio/workspaces/WorkspaceBuilder.vue'),
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
          redirect: (to) => ({
            name: 'builder',
            params: { doctype: to.params.doctype },
            query: { tab: 'workflow' },
          }),
        },
      ],
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
      ],
    },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (to.meta.public) return true
  if (!auth.isLoggedIn) return { name: 'login' }
  if (!auth.user) await auth.fetchMe()

  // Studio access check
  if (to.path.startsWith('/studio') && auth.user && !auth.user.is_superadmin) {
    return { name: 'desk' }
  }

  return true
})

export default router
