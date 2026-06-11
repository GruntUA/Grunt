import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { VueQueryPlugin } from '@tanstack/vue-query'
import PrimeVue from 'primevue/config'
import Aura from '@primevue/themes/aura'
import ToastService from 'primevue/toastservice'
import ConfirmationService from 'primevue/confirmationservice'
import Tooltip from 'primevue/tooltip'
import App from './App.vue'
import router from './router'
import i18n from './plugins/i18n'
import { grunt } from '@/core/grunt'
import { useAuthStore } from '@/stores/auth'
import '@/app-hooks'

import './assets/main.css'
import 'default-passive-events'
// Expose globally for client scripts (JS controllers)
window.grunt = grunt
window.frappe = grunt // Frappe-compatible alias

const pinia = createPinia()
const app = createApp(App)
app.use(pinia)
app.use(PrimeVue, {
  theme: {
    preset: Aura,
    options: {
      darkModeSelector: '.dark',
    },
  },
  pt: {
    // Global overrides for all Buttons
    button: {
      root: ({ props }: any) => ({
        class: props?.size === 'small' ? 'h-8 text-sm' : undefined
      })
    },
    // Unified table style
    datatable: {
      root: { class: 'rounded-lg border border-surface-200 dark:border-surface-700' },
    },
  },
  ptOptions: { mergeSections: true, mergeProps: true },
})
app.use(ToastService)
app.use(ConfirmationService)
app.directive('tooltip', Tooltip)
// Start auth request immediately — router guard will await the same promise
useAuthStore().prefetchMe()
app.use(router)
app.use(i18n)
app.use(VueQueryPlugin, {
  queryClientConfig: {
    defaultOptions: {
      queries: {
        staleTime: 60_000,
        retry: 2,
        retryDelay: 1_000,
      },
    },
  },
})
app.mount('#app')

// Register push notification service worker (production only — avoid breaking Vite HMR in dev)
if ('serviceWorker' in navigator && import.meta.env.PROD) {
  const swVersion = '2026-04-24-2'
  navigator.serviceWorker.register(`/sw.js?v=${swVersion}`).catch(() => {
    // SW registration is best-effort; push won't work but app still runs
  })
}
