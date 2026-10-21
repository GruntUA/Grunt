import { ref, computed, onMounted, onUnmounted } from 'vue'
import { notificationsApi } from '@/core/api/notifications'
import { toast } from '@/core/composables/useToast'
import { useDialog } from '@/core/composables/useDialog'
import { useTaskTracker } from '@/core/composables/useTaskTracker'
import { useAudio } from '@/core/composables/useAudio'
import { WebSocketChannel } from '@/core/ws/WebSocketChannel'
import type { GruntNotification, RealtimeEvent } from '@/types'
import i18n from '@/plugins/i18n'

const t = (key: string, params: Record<string, unknown> = {}): string => i18n.global.t(key, params)

// Shared state (singleton across components)

const notifications = ref<GruntNotification[]>([])
const unreadCount = ref(0)
const loading = ref(false)

// Notification sound - a per-browser preference, on by default.
const SOUND_KEY = 'grunt_notification_sound'
function readSoundPref(): boolean {
  try {
    return localStorage.getItem(SOUND_KEY) !== 'off'
  } catch {
    return true
  }
}
const soundEnabled = ref(readSoundPref())
const audio = useAudio()

// Custom event handler registry for user-channel WS events
type UserEventHandler = (data: Record<string, unknown>) => void
const customEventHandlers = new Map<string, Set<UserEventHandler>>()

let refCount = 0

const userChannel = new WebSocketChannel({
  url: '/api/v1/ws/user',
  includeAuthToken: true,
  pingIntervalMs: 30_000,
})

// Single wildcard handler - catches ALL events, including bulk_delete_progress/done
userChannel.on('*', (msg) => {
  const m = msg as { event: string; data?: unknown }
  handleRealtimeEvent({ event: m.event, data: (m.data ?? {}) as RealtimeEvent['data'] })
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
      // Persistent notification pushed from server - reload so the new item has its real id
      void loadNotifications()
      toast.info(msg.data.subject ?? msg.data.message ?? t('New notification'))
      if (soundEnabled.value) audio.play('chime')
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
        // Simple text - show as toast
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

    case 'progress':
    case 'task_progress': {
      // Route to the floating TaskProgressPanel (non-blocking).
      const taskTracker = useTaskTracker()
      taskTracker.update({
        task_id: msg.data.task_id as string | undefined,
        title: (msg.data.title as string) ?? t('Task'),
        count: (msg.data.count as number) ?? 0,
        total: (msg.data.total as number) ?? 100,
        percent: msg.data.percent as number | undefined,
        description: msg.data.description as string | undefined,
        unit: msg.data.unit as 'bytes' | null | undefined,
        started_at: msg.data.started_at as number | undefined,
        cancellable: msg.data.cancellable as boolean | undefined,
        step: msg.data.step as number | undefined,
        steps: msg.data.steps as number | undefined,
      })
      break
    }

    case 'task_done': {
      const taskTracker = useTaskTracker()
      taskTracker.done({
        task_id: msg.data.task_id as string | undefined,
        title: msg.data.title as string | undefined,
        status: (msg.data.status as 'done' | 'error' | 'cancelled') ?? 'done',
        message: msg.data.message as string | undefined,
        doctype: msg.data.doctype as string | null | undefined,
      })
      break
    }
  }
}

async function loadNotifications() {
  loading.value = true
  try {
    const [items, count] = await Promise.all([
      notificationsApi.list({ limit: 50 }),
      notificationsApi.unreadCount(),
    ])
    notifications.value = items
    unreadCount.value = count
  } catch (error) {
    console.error('Failed to fetch notifications', error)
  } finally {
    loading.value = false
  }
}

// Public composable

export function useNotifications() {
  const load = loadNotifications

  function setSoundEnabled(on: boolean) {
    soundEnabled.value = on
    try {
      localStorage.setItem(SOUND_KEY, on ? 'on' : 'off')
    } catch {
      // storage unavailable - the choice lasts for this tab only
    }
    if (on) audio.play('chime')
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
      void load()
      audio.preload('chime')
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
    soundEnabled: computed(() => soundEnabled.value),
    setSoundEnabled,
    load,
    markRead,
    markAllRead,
    onUserEvent,
    offUserEvent,
  }
}
