<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { RouterView } from 'vue-router'
import GruntDialog from '@/components/desk/GruntDialog.vue'
import TaskProgressPanel from '@/components/desk/TaskProgressPanel.vue'
import ErrorBoundary from '@/components/ErrorBoundary.vue'
import CommandPalette from '@/components/layout/CommandPalette.vue'
import PWAInstallPrompt from '@/components/pwa/PWAInstallPrompt.vue'
import ServerErrorModal from '@/components/debug/ServerErrorModal.vue'
import { loadRemoteTranslations } from '@/plugins/i18n'
import { useNetworkStatus, isOnline } from '@/core/composables/useNetworkStatus'
import { pendingCount } from '@/core/composables/useOfflineQueue'
import { useServerError } from '@/core/composables/useServerError'
import { useColorMode } from '@/core/composables/useColorMode'
import { WifiOff } from '@lucide/vue'
import { Toaster } from 'vue-sonner'
import { TooltipProvider } from '@/components/ui/tooltip'

const { isDark } = useColorMode()
useNetworkStatus()

const { state: serverErrorState, close: closeServerError } = useServerError()

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && serverErrorState.value.open) closeServerError()
}
onMounted(() => {
  loadRemoteTranslations()
  window.addEventListener('keydown', onKeydown)
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <TooltipProvider>
    <GruntDialog />
    <TaskProgressPanel />
    <ServerErrorModal />
    <ErrorBoundary>
      <!-- Offline banner — persistent top bar, shown only when offline -->
      <Transition enter-active-class="transition-all duration-300 ease-out" enter-from-class="-translate-y-full opacity-0"
        enter-to-class="translate-y-0 opacity-100" leave-active-class="transition-all duration-200 ease-in"
        leave-from-class="translate-y-0 opacity-100" leave-to-class="-translate-y-full opacity-0">
        <div v-if="!isOnline"
          class="fixed top-0 inset-x-0 z-200 flex items-center justify-center gap-2 px-4 py-2 bg-amber-500 text-amber-950 font-medium shadow-md">
          <WifiOff class="size-4 shrink-0" />
          <span>Немає з'єднання — зміни зберігаються локально</span>
          <span v-if="pendingCount > 0"
            class="ml-2 px-1.5 py-0.5 rounded-full bg-amber-950/15 text-xs font-semibold tabular-nums">
            {{ pendingCount }} в черзі
          </span>
        </div>
      </Transition>

      <RouterView />
      <Toaster position="bottom-right" rich-colors :theme="isDark ? 'dark' : 'light'" />

      <CommandPalette />
      <PWAInstallPrompt />
    </ErrorBoundary>
  </TooltipProvider>
</template>
