/**
 * useWebPush - Web Push API composable.
 *
 * Handles VAPID public key fetch, permission request, subscription save/remove.
 * Works only in browsers that support PushManager. Falls back gracefully.
 */

import { ref } from 'vue'
import client from '@/core/api/client'
import { toast } from '@/core/composables/useToast'
import i18n from '@/plugins/i18n'

const t = (key: string, params: Record<string, unknown> = {}): string => i18n.global.t(key, params)

const isSupported = 'serviceWorker' in navigator && 'PushManager' in window

const isSubscribed = ref(false)
const isLoading = ref(false)
const permissionState = ref<NotificationPermission>(
  'Notification' in window ? Notification.permission : 'denied'
)

async function getVapidPublicKey(): Promise<string | null> {
  try {
    const res = await client.get('/api/v1/method/grunt.api.v1.notifications.get_vapid_public_key')
    return res.data?.data ?? null
  } catch (error) {
    console.error('Failed to get VAPID key', error)
    return null
  }
}

function urlBase64ToUint8Array(base64String: string): Uint8Array<ArrayBuffer> {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = atob(base64)
  return new Uint8Array([...raw].map(c => c.charCodeAt(0))) as Uint8Array<ArrayBuffer>
}

/**
 * The SW is registered in main.ts (prod only). `serviceWorker.ready` never
 * settles when nothing is registered, so register on demand and bound the wait.
 */
async function getRegistration(timeoutMs = 10000): Promise<ServiceWorkerRegistration | null> {
  if (!isSupported) return null
  try {
    if (!(await navigator.serviceWorker.getRegistration())) {
      await navigator.serviceWorker.register('/sw.js')
    }
    return await Promise.race([
      navigator.serviceWorker.ready,
      new Promise<null>(resolve => setTimeout(() => resolve(null), timeoutMs)),
    ])
  } catch (error) {
    console.error('Service worker registration failed', error)
    return null
  }
}

async function saveSubscription(sub: PushSubscription): Promise<void> {
  const keys = sub.toJSON().keys as { p256dh: string; auth: string }
  await client.post('/api/v1/method/grunt.api.v1.notifications.subscribe_push', {
    endpoint: sub.endpoint,
    p256dh: keys.p256dh,
    auth: keys.auth,
    user_agent: navigator.userAgent,
  })
}

async function checkSubscription(): Promise<void> {
  if (!isSupported || !(await navigator.serviceWorker.getRegistration())) {
    isSubscribed.value = false
    return
  }
  const reg = await getRegistration()
  const sub = await reg?.pushManager.getSubscription()
  isSubscribed.value = !!sub
  // Re-send an existing browser subscription: the server copy may be gone
  // (expired endpoint cleanup, DB restore) while the browser still has it.
  if (sub && permissionState.value === 'granted') {
    saveSubscription(sub).catch(() => { isSubscribed.value = false })
  }
}

async function subscribe(): Promise<boolean> {
  if (!isSupported) {
    toast.error(t('Your browser does not support push notifications'))
    return false
  }

  isLoading.value = true
  try {
    const permission = await Notification.requestPermission()
    permissionState.value = permission
    if (permission !== 'granted') {
      toast.error(permission === 'denied'
        ? t('Notifications are blocked in the browser settings for this site')
        : t('You did not allow notifications'))
      return false
    }

    const vapidKey = await getVapidPublicKey()
    if (!vapidKey) {
      toast.error(t('The server is not set up for push notifications (VAPID key missing)'))
      return false
    }

    const reg = await getRegistration()
    if (!reg) {
      toast.error(t('Service Worker is not ready. Reload the page.'))
      return false
    }

    const applicationServerKey = urlBase64ToUint8Array(vapidKey)
    // A subscription made with an older VAPID key makes subscribe() throw
    // InvalidStateError - drop it first.
    const existing = await reg.pushManager.getSubscription()
    if (existing) await existing.unsubscribe()

    const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey })
    await saveSubscription(sub)

    isSubscribed.value = true
    toast.success(t('Push notifications enabled!'))
    return true
  } catch (e) {
    console.error('Push subscribe failed', e)
    toast.error(t('Subscription error:') + ' ' + (e instanceof Error ? e.message : String(e)))
    return false
  } finally {
    isLoading.value = false
  }
}

async function unsubscribe(): Promise<void> {
  isLoading.value = true
  try {
    const reg = await getRegistration()
    if (!reg) return
    const sub = await reg.pushManager.getSubscription()
    if (!sub) return

    await client.post('/api/v1/method/grunt.api.v1.notifications.unsubscribe_push', {
      endpoint: sub.endpoint
    })
    await sub.unsubscribe()
    isSubscribed.value = false
  } catch (e) {
    console.error('Push unsubscribe failed', e)
  } finally {
    isLoading.value = false
  }
}

export function useWebPush() {
  checkSubscription()
  return {
    isSupported,
    isSubscribed,
    isLoading,
    permissionState,
    subscribe,
    unsubscribe,
    checkSubscription,
  }
}
