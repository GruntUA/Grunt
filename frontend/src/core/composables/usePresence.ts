import { ref, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import type { useWebSocket } from './useWebSocket'

export interface PresenceUser {
  email: string
  full_name: string
  color: string
}

/**
 * Derives a deterministic pastel color from an email string.
 * Used to assign a consistent avatar color per user.
 */
function emailToColor(email: string): string {
  let hash = 0
  for (let i = 0; i < email.length; i++) {
    hash = email.charCodeAt(i) + ((hash << 5) - hash)
  }
  const hue = Math.abs(hash) % 360
  return `hsl(${hue}, 55%, 48%)`
}

export function initials(fullName: string): string {
  return fullName
    .split(' ')
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? '')
    .join('')
}

/**
 * Manages real-time presence and field locking for a document form.
 *
 * Pass the result of `useWebSocket(wsUrl)` so presence shares the
 * existing connection — no second WebSocket is opened.
 */
export function usePresence(ws: ReturnType<typeof useWebSocket>) {
  const auth = useAuthStore()
  const users = ref<PresenceUser[]>([])
  const fieldLocks = ref<Record<string, PresenceUser>>({})

  // Join presence as soon as the WS connects (also re-joins on reconnect).
  watch(ws.isConnected, (connected) => {
    if (connected && auth.user) {
      ws.send({
        action: 'presence_join',
        user: {
          email: auth.user.email,
          full_name: auth.user.full_name,
          color: emailToColor(auth.user.email),
        },
      })
    }
  })

  // Handle server events
  ws.onEvent('presence_update', (data) => {
    const d = data as { users: PresenceUser[] }
    // Exclude self from the displayed list
    users.value = (d.users ?? []).filter((u) => u.email !== auth.user?.email)
  })

  ws.onEvent('field_locked', (data) => {
    const d = data as { field: string; user: PresenceUser }
    if (d.user.email !== auth.user?.email) {
      fieldLocks.value = { ...fieldLocks.value, [d.field]: d.user }
    }
  })

  ws.onEvent('field_unlocked', (data) => {
    const d = data as { field: string }
    const updated = { ...fieldLocks.value }
    delete updated[d.field]
    fieldLocks.value = updated
  })

  function focusField(fieldname: string) {
    ws.send({ action: 'field_focus', field: fieldname })
  }

  function blurField(fieldname: string) {
    ws.send({ action: 'field_blur', field: fieldname })
  }

  return { users, fieldLocks, focusField, blurField, initials, emailToColor }
}
