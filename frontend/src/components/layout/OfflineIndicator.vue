<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ref, watch } from 'vue'
import { CloudUpload, WifiOff } from '@lucide/vue'
import { isDisconnected, useNetworkStatus } from '@/core/composables/useNetworkStatus'
import { flush, pendingCount, refreshQueue } from '@/core/composables/useOfflineQueue'
import { useAuthStore } from '@/stores/auth'
import { Button } from '@/components/ui/button'
import OfflineQueueSheet from './OfflineQueueSheet.vue'

/** Offline mode for the whole app: connection tracking, queue replay and its indicators. Mount once. */

const { t } = useI18n()
const auth = useAuthStore()
const queueOpen = ref(false)

useNetworkStatus()

// The queue is per user: reload it on sign-in / switch and send what's pending.
watch(
  () => auth.user?.email,
  async (email) => {
    await refreshQueue().catch(() => undefined)
    if (email && !isDisconnected.value) await flush().catch(() => undefined)
  },
  { immediate: true },
)
</script>

<template>
  <Transition enter-active-class="transition-opacity duration-300" enter-from-class="opacity-0"
    leave-active-class="transition-opacity duration-200" leave-to-class="opacity-0">
    <!-- A pill, not a full-width bar: it must never cover the page toolbar (Save). -->
    <button v-if="isDisconnected" type="button"
      class="fixed bottom-20 left-1/2 z-50 flex -translate-x-1/2 items-center gap-2 rounded-full bg-amber-500 px-4 py-2 font-medium text-amber-950 shadow-md md:bottom-4"
      @click="queueOpen = true">
      <WifiOff class="size-4 shrink-0" />
      <span>{{ t('No connection — viewing from cache, changes are saved on this device') }}</span>
      <span v-if="pendingCount > 0"
        class="ml-2 px-1.5 py-0.5 rounded-full bg-amber-950/15 font-semibold tabular-nums">
        {{ t('{n} queued', { n: String(pendingCount) }) }}
      </span>
    </button>
  </Transition>

  <!-- Online again but changes still waiting (conflicts / refused) -->
  <Button v-if="!isDisconnected && pendingCount > 0" variant="outline"
    class="fixed bottom-20 left-4 z-50 rounded-full shadow-md md:bottom-4"
    @click="queueOpen = true">
    <CloudUpload class="text-primary" />
    {{ t('{n} unsynced changes', { n: String(pendingCount) }) }}
  </Button>

  <OfflineQueueSheet v-model:open="queueOpen" />
</template>
