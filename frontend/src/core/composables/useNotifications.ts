import { ref, computed, onMounted, onUnmounted } from 'vue'
import { notificationsApi } from '@/core/api/notifications'
import { useToast } from '@/core/composables/useToast'
import { useDialog } from '@/core/composables/useDialog'
import type { GruntNotification, RealtimeEvent } from '@/types'

// ── Shared state (singleton across components) ───────────────────────────

const notifications = ref<GruntNotification[]>([])
const unreadCount = ref(0)
const loading = ref(false)

let ws: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let refCount = 0

function getWsUrl(): string {
  const base = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
  const wsBase = base.replace(/^http/, 'ws')
  const token = localStorage.getItem('grunt_token')
  return `${wsBase}/api/v1/ws/user${token ? `?token=${encodeURIComponent(token)}` : ''}`
}

function connectWs() {
  if (ws && ws.readyState <= WebSocket.OPEN) return

  const token = localStorage.getItem('grunt_token')
  if (!token) return

  ws = new WebSocket(getWsUrl())

  ws.onopen = () => {
    // Start keep-alive pings
    pingInterval = setInterval(() => {
      if (ws?.readyState === WebSocket.OPEN) {
        ws.send('{"action":"ping"}')
      }
    }, 30_000)
  }

  ws.onclose = () => {
    clearPing()
    if (refCount > 0) {
      reconnectTimer = setTimeout(connectWs, 3000)
    }
  }

  ws.onerror = () => {
    // onclose fires after onerror
  }

  ws.onmessage = (e) => {
    try {
      const msg: RealtimeEvent = JSON.parse(e.data)
      handleRealtimeEvent(msg)
    } catch {
      // ignore malformed messages
    }
  }
}

let pingInterval: ReturnType<typeof setInterval> | null = null

function clearPing() {
  if (pingInterval) {
    clearInterval(pingInterval)
    pingInterval = null
  }
}

function disconnectWs() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  clearPing()
  if (ws) {
    ws.onclose = null
    ws.close()
    ws = null
  }
}

function handleRealtimeEvent(msg: RealtimeEvent) {
  const toast = useToast()
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

  return {
    notifications: computed(() => notifications.value),
    unreadCount: computed(() => unreadCount.value),
    loading: computed(() => loading.value),
    load,
    markRead,
    markAllRead,
  }
}
