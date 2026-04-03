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
import { toast } from 'vue-sonner'

export const isOnline = ref(typeof navigator !== 'undefined' ? navigator.onLine : true)

// True if the tab went offline at least once this session (used to show
// "restored" toast only after an actual disconnect, not on first load).
const wentOffline = ref(false)

// ID of the persistent "offline" toast so we can dismiss it on reconnect
let offlineToastId: string | number | undefined

function onOffline() {
  isOnline.value = false
  wentOffline.value = true
  offlineToastId = toast.warning('Немає з\'єднання', {
    description: 'Зміни зберігаються локально та будуть синхронізовані при відновленні зв\'язку.',
    duration: Infinity,
    id: 'network-offline',
  }) as string | number
}

async function onOnline() {
  isOnline.value = true
  // Dismiss the persistent offline toast
  toast.dismiss('network-offline')

  if (wentOffline.value) {
    toast.success('Зв\'язок відновлено', {
      description: 'Синхронізуємо збережені зміни...',
      duration: 3000,
    })

    // Flush pending offline mutations
    const { offlineQueue } = await import('./useOfflineQueue')
    const synced = await offlineQueue.flush()
    if (synced > 0) {
      toast.success(`Синхронізовано ${synced} збережених ${synced === 1 ? 'зміну' : 'змін'}`, {
        duration: 4000,
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
