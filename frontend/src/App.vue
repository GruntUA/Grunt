<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useQueryClient } from '@tanstack/vue-query'
import { RouterView } from 'vue-router'
import GruntDialog from '@/components/desk/GruntDialog.vue'
import TaskProgressPanel from '@/components/desk/TaskProgressPanel.vue'
import ErrorBoundary from '@/components/ErrorBoundary.vue'
import CommandPalette from '@/components/layout/CommandPalette.vue'
import PWAInstallPrompt from '@/components/pwa/PWAInstallPrompt.vue'
import ServerErrorModal from '@/components/debug/ServerErrorModal.vue'
import { loadRemoteTranslations } from '@/plugins/i18n'
import { useNetworkStatus, isDisconnected } from '@/core/composables/useNetworkStatus'
import { flush, pendingCount, refreshQueue } from '@/core/composables/useOfflineQueue'
import OfflineQueueSheet from '@/components/layout/OfflineQueueSheet.vue'
import { useAuthStore } from '@/stores/auth'
import { useServerError } from '@/core/composables/useServerError'
import { useColorMode } from '@/core/composables/useColorMode'
import { CloudUpload, WifiOff } from '@lucide/vue'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'

const { isDark } = useColorMode()
useNetworkStatus()

const { state: serverErrorState, close: closeServerError } = useServerError()

// Offline changes: reload the signed-in user's queue and send what's pending;
// refresh cached queries once the server accepted something.
const queueOpen = ref(false)
const auth = useAuthStore()
const queryClient = useQueryClient()
watch(
  () => auth.user?.email,
  async (email) => {
    await refreshQueue().catch(() => undefined)
    if (email && !isDisconnected.value) await flush().catch(() => undefined)
  },
  { immediate: true },
)
function onSynced() {
  void queryClient.invalidateQueries()
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && serverErrorState.value.open) closeServerError()
}
onMounted(() => {
  loadRemoteTranslations()
  window.addEventListener('keydown', onKeydown)
  window.addEventListener('grunt:offline-synced', onSynced)
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('grunt:offline-synced', onSynced)
})
</script>

<template>
  <TooltipProvider>
    <GruntDialog />
    <TaskProgressPanel />
    <ServerErrorModal />
    <ErrorBoundary>
      <!-- Offline banner — persistent top bar, shown only when offline -->
      <Transition enter-active-class="transition-opacity duration-300" enter-from-class="opacity-0"
        leave-active-class="transition-opacity duration-200" leave-to-class="opacity-0">
        <!-- A pill, not a full-width bar: it must never cover the page toolbar (Save). -->
        <button v-if="isDisconnected" type="button"
          class="fixed bottom-20 left-1/2 z-50 flex -translate-x-1/2 items-center gap-2 rounded-full bg-amber-500 px-4 py-2 font-medium text-amber-950 shadow-md md:bottom-4"
          @click="queueOpen = true">
          <WifiOff class="size-4 shrink-0" />
          <span>Немає з'єднання — перегляд з кешу, зміни зберігаються на пристрої</span>
          <span v-if="pendingCount > 0"
            class="ml-2 px-1.5 py-0.5 rounded-full bg-amber-950/15 font-semibold tabular-nums">
            {{ pendingCount }} в черзі
          </span>
        </button>
      </Transition>

      <!-- Online again but changes still waiting (conflicts / refused) -->
      <button v-if="!isDisconnected && pendingCount > 0" type="button"
        class="fixed bottom-20 left-4 z-50 flex items-center gap-2 rounded-full border bg-card px-3 py-1.5 font-medium shadow-md md:bottom-4"
        @click="queueOpen = true">
        <CloudUpload class="size-4 text-primary" />
        {{ pendingCount }} несинхронізованих змін
      </button>
      <OfflineQueueSheet v-model:open="queueOpen" />

      <RouterView />
      <Toaster position="bottom-right" :theme="isDark ? 'dark' : 'light'" />

      <CommandPalette />
      <PWAInstallPrompt />
    </ErrorBoundary>
  </TooltipProvider>
</template>
