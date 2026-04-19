import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { VueQueryPlugin } from '@tanstack/vue-query'
import PrimeVue from 'primevue/config'
import Aura from '@primevue/themes/aura'
import ToastService from 'primevue/toastservice'
import ConfirmationService from 'primevue/confirmationservice'
import Tooltip from 'primevue/tooltip'
import 'primeicons/primeicons.css'
import App from './App.vue'
import router from './router'
import i18n from './plugins/i18n'
import { grunt } from '@/core/grunt'
import { useAuthStore } from '@/stores/auth'
import '@/app-hooks'
import './assets/main.css'
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

// Register push notification service worker
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(() => {
    // SW registration is best-effort; push won't work but app still runs
  })
}
