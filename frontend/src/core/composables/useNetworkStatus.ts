/**
 * useNetworkStatus — is the app connected, and when did it come back?
 *
 * Two signals, because `navigator.onLine` only knows about the local network:
 *  - `isOnline`        — the browser's own online/offline state;
 *  - `serverReachable` — whether the last API call reached the server. It turns
 *    false on a network error or when the service worker answered from its
 *    offline cache (`X-Grunt-Offline` header), true on any real response.
 *
 * Coming back (either signal) sends the offline change queue; while the
 * server is away or changes are waiting, sending is retried every 30 s.
 *
 * Call useNetworkStatus() once in App.vue; the refs are module-level singletons.
 */

import { computed, onMounted, onUnmounted, ref } from 'vue'
import { toast } from '@/core/composables/useToast'

export const isOnline = ref(typeof navigator !== 'undefined' ? navigator.onLine : true)
export const serverReachable = ref(true)
/** What the UI should treat as "offline". */
export const isDisconnected = computed(() => !isOnline.value || !serverReachable.value)

const RETRY_MS = 30_000
let wentOffline = false

function announceOffline() {
  if (wentOffline) return
  wentOffline = true
  toast.warning("Немає з'єднання", "З'єднання", {
    detail: 'Відкриті раніше сторінки доступні для перегляду; зміни документів збережуться на пристрої й надішлються після відновлення зв\'язку.',
    sticky: true,
    group: 'network',
  })
}

async function sync() {
  const { offlineQueue, queue } = await import('./useOfflineQueue')
  if (!queue.value.some((c) => c.status === 'pending')) return
  const synced = await offlineQueue.flush()
  if (synced > 0) {
    toast.success(`Синхронізовано ${synced} збережених ${synced === 1 ? 'зміну' : 'змін'}`, 'Синхронізація', {
      life: 4000,
    })
  }
}

async function comeBack() {
  if (isDisconnected.value) return
  toast.removeGroup('network')
  if (wentOffline) {
    wentOffline = false
    toast.success("Зв'язок відновлено", "З'єднання")
  }
  await sync()
}

/** Report the outcome of an API call (see api/client.ts). */
export function markServerReachable(reachable: boolean) {
  if (serverReachable.value === reachable) return
  serverReachable.value = reachable
  if (reachable) void comeBack()
  else announceOffline()
}

function onOffline() {
  isOnline.value = false
  announceOffline()
}

function onOnline() {
  isOnline.value = true
  void comeBack()
}

export function useNetworkStatus() {
  let timer: ReturnType<typeof setInterval> | undefined

  onMounted(() => {
    window.addEventListener('online', onOnline)
    window.addEventListener('offline', onOffline)
    if (!navigator.onLine) onOffline()
    // Server outages don't fire browser events — keep retrying the queue.
    timer = setInterval(() => void sync().catch(() => undefined), RETRY_MS)
  })

  onUnmounted(() => {
    window.removeEventListener('online', onOnline)
    window.removeEventListener('offline', onOffline)
    clearInterval(timer)
  })

  return { isOnline, serverReachable, isDisconnected }
}
