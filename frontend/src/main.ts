import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { VueQueryPlugin } from '@tanstack/vue-query'
import App from './App.vue'
import router from './router'
import i18n, { loadRemoteTranslations } from './plugins/i18n'
import { vueQueryOptions } from './plugins/vueQuery'
import { grunt } from '@/core/grunt'
import { useAuthStore } from '@/stores/auth'
import { loadSiteConfig } from '@/core/composables/useSiteConfig'
import { ensureDeviceId } from '@/core/deviceId'
import '@/app-hooks'

import '@fontsource-variable/inter'
import './assets/main.css'
import 'vue-sonner/style.css'
// Expose globally for client scripts (JS controllers)
window.grunt = grunt
ensureDeviceId()

const pinia = createPinia()
const app = createApp(App)
app.use(pinia)
// Kick off boot requests immediately - the router guard awaits the same
// promises before resolving the first route.
useAuthStore().prefetchMe()
loadSiteConfig()
app.use(router)
app.use(i18n)
loadRemoteTranslations()
app.use(VueQueryPlugin, vueQueryOptions)
app.mount('#app')

// Register push notification service worker (production only - avoid breaking Vite HMR in dev)
if ('serviceWorker' in navigator && import.meta.env.PROD) {
  const swVersion = '2026-04-24-2'
  navigator.serviceWorker.register(`/sw.js?v=${swVersion}`).catch(() => {
    // SW registration is best-effort; push won't work but app still runs
  })
} else if ('serviceWorker' in navigator) {
  // A worker left over from a prod build on the same origin would serve stale dev modules.
  void navigator.serviceWorker.getRegistrations().then((regs) => regs.forEach((r) => r.unregister()))
}
