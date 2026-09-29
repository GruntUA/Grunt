<script setup lang="ts">
import { useI18n } from 'vue-i18n'
/**
 * PWAInstallPrompt — shows the browser "Add to Home Screen" install button.
 *
 * The component listens for the `beforeinstallprompt` event (Chrome / Android).
 * On iOS Safari the `beforeinstallprompt` is not fired — we detect that separately
 * and show a manual instruction sheet.
 *
 * Usage: drop once in App.vue.
 */
import { ref, onMounted, onUnmounted } from 'vue'
import { Download, X, Share, PlusSquare } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { useSiteConfig } from '@/core/composables/useSiteConfig'

const { t } = useI18n()

const { appName } = useSiteConfig()

// ── State ──────────────────────────────────────────────────────────────────

type InstallState = 'hidden' | 'available' | 'ios-hint'

const state = ref<InstallState>('hidden')
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let deferredPrompt: any = null

const DISMISSED_KEY = 'grunt_pwa_install_dismissed'

// ── Detection ──────────────────────────────────────────────────────────────

function isStandalone() {
  return (
    window.matchMedia('(display-mode: standalone)').matches ||
    ('standalone' in navigator && (navigator as { standalone?: boolean }).standalone === true)
  )
}

function isIOS() {
  return /iphone|ipad|ipod/i.test(navigator.userAgent) && !(window as Window & { MSStream?: unknown }).MSStream
}

function wasDismissed() {
  return localStorage.getItem(DISMISSED_KEY) === '1'
}

function onBeforeInstallPrompt(e: Event) {
  if (wasDismissed()) return
  e.preventDefault()
  deferredPrompt = e
  state.value = 'available'
}

onMounted(() => {
  if (isStandalone() || wasDismissed()) return
  window.addEventListener('beforeinstallprompt', onBeforeInstallPrompt)
  // iOS: no beforeinstallprompt event — show hint on mobile Safari
  if (isIOS() && !isStandalone()) {
    setTimeout(() => { if (!wasDismissed()) state.value = 'ios-hint' }, 3000)
  }
})

onUnmounted(() => {
  window.removeEventListener('beforeinstallprompt', onBeforeInstallPrompt)
})

// ── Actions ────────────────────────────────────────────────────────────────

async function install() {
  if (!deferredPrompt) return
  deferredPrompt.prompt()
  const { outcome } = await deferredPrompt.userChoice
  deferredPrompt = null
  if (outcome === 'accepted') {
    state.value = 'hidden'
  }
}

function dismiss() {
  localStorage.setItem(DISMISSED_KEY, '1')
  state.value = 'hidden'
}
</script>

<template>
  <!-- Android / Chrome: native install banner -->
  <Transition
    enter-active-class="transition-all duration-300 ease-out"
    enter-from-class="translate-y-full opacity-0"
    enter-to-class="translate-y-0 opacity-100"
    leave-active-class="transition-all duration-200 ease-in"
    leave-from-class="translate-y-0 opacity-100"
    leave-to-class="translate-y-full opacity-0"
  >
    <div
      v-if="state === 'available'"
      class="fixed bottom-4 inset-x-4 z-[150] flex items-center gap-3 p-4 bg-card border border-border/60 rounded-lg shadow-md max-w-sm mx-auto"
    >
      <div class="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
        <Download class="w-5 h-5 text-primary" />
      </div>
      <div class="flex-1 min-w-0">
        <p class="font-semibold text-foreground leading-tight">{{ t('Install {app}', { app: appName }) }}</p>
        <p class="text-muted-foreground mt-0.5">{{ t('Add to the home screen for quick access') }}</p>
      </div>
      <div class="flex items-center gap-1.5 shrink-0">
        <Button size="sm" @click="install">{{ t('Yes') }}</Button>
        <button class="p-1.5 rounded-md hover:bg-muted transition-colors" @click="dismiss">
          <X class="w-4 h-4 text-muted-foreground" />
        </button>
      </div>
    </div>
  </Transition>

  <!-- iOS Safari: manual instruction sheet -->
  <Transition
    enter-active-class="transition-all duration-300 ease-out"
    enter-from-class="translate-y-full opacity-0"
    enter-to-class="translate-y-0 opacity-100"
    leave-active-class="transition-all duration-200 ease-in"
    leave-from-class="translate-y-0 opacity-100"
    leave-to-class="translate-y-full opacity-0"
  >
    <div
      v-if="state === 'ios-hint'"
      class="fixed bottom-4 inset-x-4 z-[150] p-4 bg-card border border-border/60 rounded-lg shadow-md max-w-sm mx-auto"
    >
      <div class="flex items-start justify-between mb-3">
        <p class="font-semibold text-foreground">{{ t('Install on iPhone / iPad') }}</p>
        <button class="p-1 rounded-md hover:bg-muted transition-colors" @click="dismiss">
          <X class="w-4 h-4 text-muted-foreground" />
        </button>
      </div>
      <ol class="space-y-2 text-muted-foreground">
        <li class="flex items-center gap-2">
          <Share class="w-4 h-4 shrink-0 text-blue-500" />
          <span>{{ t('Tap') }} <strong class="text-foreground">{{ t('Share') }}</strong> {{ t('in Safari') }}</span>
        </li>
        <li class="flex items-center gap-2">
          <PlusSquare class="w-4 h-4 shrink-0 text-blue-500" />
          <span>{{ t('Choose') }} <strong class="text-foreground">{{ t('Add to Home Screen') }}</strong></span>
        </li>
      </ol>
    </div>
  </Transition>
</template>
