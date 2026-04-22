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
import { onMounted, onUnmounted } from 'vue'

import { WebSocketChannel } from '@/core/ws/WebSocketChannel'

export function usePublicWebSocket(channel: string) {
  const socketChannel = new WebSocketChannel({
    url: `/api/v1/ws/public/${channel}`,
    includeAuthToken: false,
    pingIntervalMs: 30_000,
  })

  onMounted(() => socketChannel.connect())

  onUnmounted(() => {
    socketChannel.destroy()
  })

  return {
    isConnected: socketChannel.isConnected,
    lastMessage: socketChannel.lastMessage,
    onEvent: (event: string, handler: (data: Record<string, unknown>) => void) => {
      return socketChannel.on(event, (data) => handler((data ?? {}) as Record<string, unknown>))
    },
    send: (data: unknown) => socketChannel.send(data),
  }
}
