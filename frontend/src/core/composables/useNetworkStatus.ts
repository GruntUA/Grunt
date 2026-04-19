/**
 * useNetworkStatus — reactive network connectivity tracking.
 *
 * - Watches `navigator.onLine` + browser `online`/`offline` events
 * - Shows Sonner toasts: persistent warning when offline, success when restored
 * - Flushes the offline mutation queue when connection is restored
 *
 * Call once in App.vue; the returned refs are module-level singletons.
 */

import { ref, onMounted, onUnmounted } from 'vue'
import { toast } from '@/core/composables/useToast'

export const isOnline = ref(typeof navigator !== 'undefined' ? navigator.onLine : true)

// True if the tab went offline at least once this session (used to show
// "restored" toast only after an actual disconnect, not on first load).
const wentOffline = ref(false)

function onOffline() {
  isOnline.value = false
  wentOffline.value = true
  toast.warning('Немає з\'єднання', "З'єднання", {
    detail: 'Зміни зберігаються локально та будуть синхронізовані при відновленні зв\'язку.',
    sticky: true,
    group: 'network',
  })
}

async function onOnline() {
  isOnline.value = true
  // Dismiss the persistent offline toast
  toast.removeGroup('network')

  if (wentOffline.value) {
    toast.success("Зв'язок відновлено", "З'єднання")

    // Flush pending offline mutations
    const { offlineQueue } = await import('./useOfflineQueue')
    const synced = await offlineQueue.flush()
    if (synced > 0) {
      toast.success(`Синхронізовано ${synced} збережених ${synced === 1 ? 'зміну' : 'змін'}`, "Синхронізація", {
        life: 4000,
      })
    }
  }
}

export function useNetworkStatus() {
  onMounted(() => {
    window.addEventListener('online', onOnline)
    window.addEventListener('offline', onOffline)

    // Sync initial state in case it changed before mount
    if (!navigator.onLine && isOnline.value) onOffline()
  })

  onUnmounted(() => {
    window.removeEventListener('online', onOnline)
    window.removeEventListener('offline', onOffline)
  })

  return { isOnline, wentOffline }
}
