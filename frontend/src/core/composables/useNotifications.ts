import { ref, computed, onMounted, onUnmounted } from 'vue'
import { notificationsApi } from '@/core/api/notifications'
import { toast } from '@/core/composables/useToast'
import { useDialog } from '@/core/composables/useDialog'
import { WebSocketChannel } from '@/core/ws/WebSocketChannel'
import type { GruntNotification, RealtimeEvent } from '@/types'

// ── Shared state (singleton across components) ───────────────────────────

const notifications = ref<GruntNotification[]>([])
const unreadCount = ref(0)
const loading = ref(false)

// Custom event handler registry for user-channel WS events
type UserEventHandler = (data: Record<string, unknown>) => void
const customEventHandlers = new Map<string, Set<UserEventHandler>>()

let refCount = 0

const userChannel = new WebSocketChannel({
  url: '/api/v1/ws/user',
  includeAuthToken: true,
  pingIntervalMs: 30_000,
})

userChannel.on('notification', (data) => {
  handleRealtimeEvent({ event: 'notification', data: (data ?? {}) as RealtimeEvent['data'] })
})
userChannel.on('msgprint', (data) => {
  handleRealtimeEvent({ event: 'msgprint', data: (data ?? {}) as RealtimeEvent['data'] })
})
userChannel.on('alert', (data) => {
  handleRealtimeEvent({ event: 'alert', data: (data ?? {}) as RealtimeEvent['data'] })
})
userChannel.on('progress', (data) => {
  handleRealtimeEvent({ event: 'progress', data: (data ?? {}) as RealtimeEvent['data'] })
})

function connectWs() {
  if (!localStorage.getItem('grunt_token')) {
    return
  }

  userChannel.connect()
}

function disconnectWs() {
  userChannel.disconnect()
}

function handleRealtimeEvent(msg: RealtimeEvent) {
  // Dispatch to custom handlers first (e.g. bulk_delete_progress)
  const custom = customEventHandlers.get(msg.event)
  if (custom?.size) {
    for (const handler of custom) handler(msg.data as Record<string, unknown>)
    return
  }

  const dialog = useDialog()

  switch (msg.event) {
    case 'notification': {
      // Persistent notification pushed from server — refresh list
      unreadCount.value++
      if (msg.data.subject) {
        notifications.value.unshift({
          id: String(Date.now()),
          subject: msg.data.subject ?? '',
          message: msg.data.message ?? '',
          doctype: msg.data.doctype ?? null,
          doc_id: msg.data.doc_id ?? null,
          is_read: false,
          created_at: new Date().toISOString(),
        })
      }
      // Show a toast for the notification
      toast.info(msg.data.subject ?? msg.data.message ?? 'Нове сповіщення')
      break
    }

    case 'msgprint': {
      // Server-pushed message dialog
      const text = msg.data.message ?? ''
      if (msg.data.title || msg.data.indicator) {
        dialog.msgprint({
          message: text,
          title: msg.data.title as string | undefined,
          indicator: msg.data.indicator as string | undefined,
        })
      } else {
        // Simple text — show as toast
        const type = msg.data.type ?? 'info'
        if (type === 'error') toast.error(text)
        else if (type === 'success') toast.success(text)
        else toast.info(text)
      }
      break
    }

    case 'alert': {
      const type = msg.data.type ?? 'info'
      const text = msg.data.message ?? ''
      if (type === 'error') toast.error(text)
      else if (type === 'success') toast.success(text)
      else toast.info(text)
      break
    }

    case 'progress': {
      dialog.progress(
        (msg.data.title as string) ?? 'Прогрес',
        (msg.data.count as number) ?? 0,
        (msg.data.total as number) ?? 100,
        msg.data.description as string | undefined,
      )
      break
    }
  }
}

// ── Public composable ────────────────────────────────────────────────────

export function useNotifications() {
  async function load() {
    loading.value = true
    try {
      const [items, count] = await Promise.all([
        notificationsApi.list({ limit: 20 }),
        notificationsApi.unreadCount(),
      ])
      notifications.value = items
      unreadCount.value = count
    } finally {
      loading.value = false
    }
  }

  async function markRead(id: string) {
    await notificationsApi.markRead(id)
    const item = notifications.value.find(n => n.id === id)
    if (item && !item.is_read) {
      item.is_read = true
      unreadCount.value = Math.max(0, unreadCount.value - 1)
    }
  }

  async function markAllRead() {
    await notificationsApi.markAllRead()
    notifications.value.forEach(n => (n.is_read = true))
    unreadCount.value = 0
  }

  // Lifecycle: connect/disconnect WS based on component mount count
  onMounted(() => {
    refCount++
    if (refCount === 1) {
      connectWs()
      load()
    }
  })

  onUnmounted(() => {
    refCount--
    if (refCount <= 0) {
      refCount = 0
      disconnectWs()
    }
  })

  function onUserEvent(event: string, handler: UserEventHandler) {
    if (!customEventHandlers.has(event)) customEventHandlers.set(event, new Set())
    customEventHandlers.get(event)!.add(handler)
  }

  function offUserEvent(event: string, handler: UserEventHandler) {
    customEventHandlers.get(event)?.delete(handler)
  }

  return {
    notifications: computed(() => notifications.value),
    unreadCount: computed(() => unreadCount.value),
    loading: computed(() => loading.value),
    load,
    markRead,
    markAllRead,
    onUserEvent,
    offUserEvent,
  }
}
