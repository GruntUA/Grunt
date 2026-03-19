import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = createRouter({
    history: createWebHistory(),
    routes: [
        {
            path: '/',
            redirect: '/desk',
        },
        {
            path: '/login',
            name: 'Login',
            component: () => import('../pages/auth/Login.vue'),
            meta: { requiresGuest: true },
        },
        {
            path: '/desk',
            component: () => import('../pages/desk/DeskHome.vue'),
            meta: { requiresAuth: true },
            children: [
                {
                    path: '',
                    name: 'DeskRoot',
                    component: { template: '<div class="p-8 text-center text-gray-500">Виберіть розділ меню зліва.</div>' }
                },
                {
                    path: ':doctype',
                    name: 'ListView',
                    component: () => import('../pages/desk/[doctype]/ListView.vue'),
                },
                {
                    path: ':doctype/:id',
                    name: 'FormView',
                    component: () => import('../pages/desk/[doctype]/FormView.vue'),
                }
            ]
        }
    ],
})

router.beforeEach(async (to, from, next) => {
    const authStore = useAuthStore()
    const token = localStorage.getItem('token')

    if (token && !authStore.user && !authStore.token) {
        authStore.token = token
    }

    const isAuthenticated = !!authStore.token

    if (to.meta.requiresAuth && !isAuthenticated) {
        next('/login')
    } else if (to.meta.requiresGuest && isAuthenticated) {
        next('/desk')
    } else {
        next()
    }
})

export default router
