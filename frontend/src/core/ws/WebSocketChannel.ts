import { ref } from 'vue'

import { refreshSession } from '@/core/api/client'
import { isJwtExpired } from '@/core/jwt'

type EventHandler = (data: unknown) => void

interface WebSocketChannelOptions {
  url: string | null
  includeAuthToken?: boolean
  reconnectDelayMs?: number
  pingIntervalMs?: number
  pingPayload?: unknown
}

/** Subprotocol name the server answers with; the JWT rides as the second
 * offered protocol so it never lands in a URL (and so in access logs). */
const AUTH_SUBPROTOCOL = 'grunt.auth'

export function buildWebSocketUrl(url: string): string {
  if (url.startsWith('ws://') || url.startsWith('wss://')) {
    return url
  }
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${location.host}${url}`
}

/** `Sec-WebSocket-Protocol` offer carrying the stored JWT, or `undefined` without one. */
export function authProtocols(): string[] | undefined {
  const token = localStorage.getItem('grunt_token')
  return token ? [AUTH_SUBPROTOCOL, token] : undefined
}

/** Open channels across the app - each component owns its own WebSocketChannel. */
const openChannels = new Set<WebSocketChannel>()

/** How many of the app's channels to `url` are open right now (health report). */
export function openChannelCount(url: string): number {
  return [...openChannels].filter((c) => c.channelUrl === url).length
}

export class WebSocketChannel {
  readonly isConnected = ref(false)
  readonly lastMessage = ref<unknown>(null)

  private ws: WebSocket | null = null
  private url: string | null

  get channelUrl(): string | null {
    return this.url
  }
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private pingTimer: ReturnType<typeof setInterval> | null = null
  private manualClose = false
  private refreshing = false
  private readonly eventHandlers = new Map<string, Set<EventHandler>>()
  private readonly includeAuthToken: boolean
  private readonly reconnectDelayMs: number
  private readonly pingIntervalMs: number | null
  private readonly pingPayload: unknown

  constructor(options: WebSocketChannelOptions) {
    this.url = options.url
    this.includeAuthToken = options.includeAuthToken ?? true
    this.reconnectDelayMs = options.reconnectDelayMs ?? 3000
    this.pingIntervalMs = options.pingIntervalMs ?? null
    this.pingPayload = options.pingPayload ?? { action: 'ping' }
  }

  setUrl(url: string | null) {
    if (this.url === url) {
      return
    }

    this.url = url
    if (!url) {
      this.disconnect()
      return
    }

    this.reconnect()
  }

  connect() {
    if (!this.url) {
      this.disconnect()
      return
    }

    const token = this.includeAuthToken ? localStorage.getItem('grunt_token') : null
    if (this.includeAuthToken && !token) {
      this.disconnect()
      return
    }

    if (this.ws?.readyState === WebSocket.OPEN || this.ws?.readyState === WebSocket.CONNECTING) {
      return
    }

    this.manualClose = false
    // A rejected handshake reaches the browser only as code 1006, so an
    // expired access token would be retried forever - renew it first, the
    // same way the HTTP client does on a 401.
    if (token && isJwtExpired(token)) {
      if (this.refreshing) return
      this.refreshing = true
      void refreshSession().then((ok) => {
        this.refreshing = false
        if (ok && !this.manualClose) this.connect()
      })
      return
    }

    const fullUrl = buildWebSocketUrl(this.url)
    this.ws = new WebSocket(fullUrl, this.includeAuthToken ? authProtocols() : undefined)

    this.ws.onopen = () => {
      this.isConnected.value = true
      openChannels.add(this)
      this.startPing()
    }

    this.ws.onclose = () => {
      this.isConnected.value = false
      openChannels.delete(this)
      this.stopPing()
      this.ws = null

      if (!this.manualClose && this.url) {
        this.stopReconnect()
        this.reconnectTimer = setTimeout(() => this.connect(), this.reconnectDelayMs)
      }
    }

    this.ws.onerror = () => {
      // onclose fires after onerror in browsers
    }

    this.ws.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data)
        if (parsed?.event === 'pong') {
          return
        }

        this.lastMessage.value = parsed
        if (parsed?.event) {
          // Dispatch to specific event handlers
          const handlers = this.eventHandlers.get(parsed.event)
          if (handlers) {
            for (const handler of handlers) {
              handler(parsed.data)
            }
          }
          // Dispatch to wildcard handlers (receive the full parsed message)
          const wildcardHandlers = this.eventHandlers.get('*')
          if (wildcardHandlers) {
            for (const handler of wildcardHandlers) {
              handler(parsed)
            }
          }
        }
      } catch {
        this.lastMessage.value = event.data
      }
    }
  }

  disconnect() {
    this.manualClose = true
    this.stopReconnect()
    this.stopPing()
    this.isConnected.value = false
    openChannels.delete(this)

    if (this.ws) {
      const ws = this.ws
      ws.onclose = null
      ws.onmessage = null
      if (ws.readyState === WebSocket.CONNECTING) {
        // Closing a CONNECTING socket logs a browser warning - defer until open
        ws.onopen = () => ws.close()
      } else {
        ws.close()
      }
      this.ws = null
    }
  }

  reconnect() {
    this.disconnect()
    this.manualClose = false
    this.connect()
  }

  destroy() {
    this.disconnect()
    this.eventHandlers.clear()
    this.lastMessage.value = null
  }

  send(data: unknown) {
    if (this.ws?.readyState !== WebSocket.OPEN) {
      return
    }

    if (typeof data === 'string') {
      this.ws.send(data)
      return
    }

    this.ws.send(JSON.stringify(data))
  }

  on(eventName: string, handler: EventHandler) {
    if (!this.eventHandlers.has(eventName)) {
      this.eventHandlers.set(eventName, new Set())
    }
    this.eventHandlers.get(eventName)!.add(handler)
    return () => this.off(eventName, handler)
  }

  off(eventName: string, handler: EventHandler) {
    const handlers = this.eventHandlers.get(eventName)
    if (!handlers) {
      return
    }

    handlers.delete(handler)
    if (handlers.size === 0) {
      this.eventHandlers.delete(eventName)
    }
  }

  private startPing() {
    if (!this.pingIntervalMs) {
      return
    }

    this.stopPing()
    this.pingTimer = setInterval(() => {
      this.send(this.pingPayload)
    }, this.pingIntervalMs)
  }

  private stopPing() {
    if (this.pingTimer) {
      clearInterval(this.pingTimer)
      this.pingTimer = null
    }
  }

  private stopReconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
  }
}