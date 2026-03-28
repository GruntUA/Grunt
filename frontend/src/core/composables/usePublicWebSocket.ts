/**
 * Public (unauthenticated) WebSocket composable.
 *
 * Connects to `/api/v1/ws/public/{channel}` without a JWT token.
 * Used for public displays like queue boards, kiosk screens, etc.
 *
 * Usage:
 * ```ts
 * const { onEvent, isConnected } = usePublicWebSocket('queue:board')
 * onEvent('ticket_called', (data) => { ... })
 * ```
 */
import { ref, onMounted, onUnmounted } from 'vue'

interface WsMessage {
  event: string
  data: Record<string, unknown>
}

export function usePublicWebSocket(channel: string) {
  const isConnected = ref(false)
  const lastMessage = ref<WsMessage | null>(null)

  let ws: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let pingTimer: ReturnType<typeof setInterval> | null = null
  let manualClose = false

  const listeners = new Map<string, Set<(data: Record<string, unknown>) => void>>()

  function connect() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${proto}//${location.host}/api/v1/ws/public/${channel}`

    ws = new WebSocket(url)

    ws.onopen = () => {
      isConnected.value = true
      // Keep-alive ping every 30s
      pingTimer = setInterval(() => {
        if (ws?.readyState === WebSocket.OPEN) {
          ws.send('{"action":"ping"}')
        }
      }, 30_000)
    }

    ws.onclose = () => {
      isConnected.value = false
      if (pingTimer) clearInterval(pingTimer)
      if (!manualClose) {
        reconnectTimer = setTimeout(connect, 3000)
      }
    }

    ws.onerror = () => {
      // close event fires after error
    }

    ws.onmessage = (e) => {
      try {
        const msg: WsMessage = JSON.parse(e.data)
        if (msg.event === 'pong') return
        lastMessage.value = msg
        const handlers = listeners.get(msg.event)
        if (handlers) {
          for (const handler of handlers) {
            handler(msg.data)
          }
        }
      } catch {
        // ignore malformed messages
      }
    }
  }

  function onEvent(event: string, handler: (data: Record<string, unknown>) => void) {
    if (!listeners.has(event)) {
      listeners.set(event, new Set())
    }
    listeners.get(event)!.add(handler)
  }

  function send(data: unknown) {
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(data))
    }
  }

  onMounted(connect)

  onUnmounted(() => {
    manualClose = true
    if (reconnectTimer) clearTimeout(reconnectTimer)
    if (pingTimer) clearInterval(pingTimer)
    ws?.close()
  })

  return { isConnected, lastMessage, onEvent, send }
}
