/**
 * useWebPush — Web Push API composable.
 *
 * Handles VAPID public key fetch, permission request, subscription save/remove.
 * Works only in browsers that support PushManager. Falls back gracefully.
 */

import { ref } from 'vue'
import client from '@/core/api/client'
import { toast } from '@/core/composables/useToast'

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

async function getRegistration(): Promise<ServiceWorkerRegistration | null> {
  if (!isSupported) return null
  try {
    return await navigator.serviceWorker.ready
  } catch {
    return null
  }
}

async function checkSubscription(): Promise<void> {
  const reg = await getRegistration()
  if (!reg) { isSubscribed.value = false; return }
  const sub = await reg.pushManager.getSubscription()
  isSubscribed.value = !!sub
}

async function subscribe(): Promise<boolean> {

  if (!isSupported) {
    toast.error('Ваш браузер не підтримує Push-сповіщення')
    return false
  }
  
  isLoading.value = true
  try {
    // Request permission
    const permission = await Notification.requestPermission()
    permissionState.value = permission
    if (permission !== 'granted') {
      toast.error('Ви не надали дозвіл на сповіщення')
      return false
    }

    const vapidKey = await getVapidPublicKey()
    if (!vapidKey) {
      toast.error('Сервер не налаштовано для Push-сповіщень (відсутній VAPID ключ)')
      return false
    }

    const reg = await getRegistration()
    if (!reg) {
      toast.error('Service Worker не готовий. Перезавантажте сторінку.')
      return false
    }

    const sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(vapidKey),
    })

    const json = sub.toJSON()
    const keys = json.keys as { p256dh: string; auth: string }

    await client.post('/api/v1/method/grunt.api.v1.notifications.subscribe_push', {
      endpoint: sub.endpoint,
      p256dh: keys.p256dh,
      auth: keys.auth,
    })

    isSubscribed.value = true
    toast.success('Push-сповіщення успішно ввімкнено!')
    return true
  } catch (e) {
    console.error('Push subscribe failed', e)
    toast.error('Помилка підписки: ' + String(e))
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

    // const json = sub.toJSON()
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
