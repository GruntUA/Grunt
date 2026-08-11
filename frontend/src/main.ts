import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { VueQueryPlugin } from '@tanstack/vue-query'
import App from './App.vue'
import router from './router'
import i18n from './plugins/i18n'
import { grunt } from '@/core/grunt'
import { useAuthStore } from '@/stores/auth'
import '@/app-hooks'

import './assets/main.css'
import 'vue-sonner/style.css'
// Expose globally for client scripts (JS controllers)
window.grunt = grunt
window.frappe = grunt // Frappe-compatible alias

const pinia = createPinia()
const app = createApp(App)
app.use(pinia)
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
