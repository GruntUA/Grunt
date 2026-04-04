import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { VueQueryPlugin } from '@tanstack/vue-query'
import App from './App.vue'
import router from './router'
import i18n from './i18n'
import { grunt } from '@/core/grunt'
import './assets/main.css'

// Expose globally for client scripts (JS controllers)
window.grunt = grunt
window.frappe = grunt // Frappe-compatible alias

const app = createApp(App)
app.use(createPinia())
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

// Register push notification service worker
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(() => {
    // SW registration is best-effort; push won't work but app still runs
  })
}
