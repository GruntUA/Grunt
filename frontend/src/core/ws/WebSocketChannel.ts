import { ref } from 'vue'

type EventHandler = (data: unknown) => void

interface WebSocketChannelOptions {
  url: string | null
  includeAuthToken?: boolean
  reconnectDelayMs?: number
  pingIntervalMs?: number
  pingPayload?: unknown
}

function buildWebSocketUrl(url: string, includeAuthToken: boolean): string {
  if (url.startsWith('ws://') || url.startsWith('wss://')) {
    return url
  }

  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
  let fullUrl = `${proto}//${location.host}${url}`

  if (!includeAuthToken) {
    return fullUrl
  }

  const token = localStorage.getItem('grunt_token')
  if (!token) {
    return fullUrl
  }

  const sep = fullUrl.includes('?') ? '&' : '?'
  fullUrl += `${sep}token=${encodeURIComponent(token)}`
  return fullUrl
}

export class WebSocketChannel {
  readonly isConnected = ref(false)
  readonly lastMessage = ref<unknown>(null)

  private ws: WebSocket | null = null
  private url: string | null
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private pingTimer: ReturnType<typeof setInterval> | null = null
  private manualClose = false
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

    if (this.includeAuthToken && !localStorage.getItem('grunt_token')) {
      this.disconnect()
      return
    }

    if (this.ws?.readyState === WebSocket.OPEN || this.ws?.readyState === WebSocket.CONNECTING) {
      return
    }

    this.manualClose = false
    const fullUrl = buildWebSocketUrl(this.url, this.includeAuthToken)
    this.ws = new WebSocket(fullUrl)

    this.ws.onopen = () => {
      this.isConnected.value = true
      this.startPing()
    }

    this.ws.onclose = () => {
      this.isConnected.value = false
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

    if (this.ws) {
      const ws = this.ws
      ws.onclose = null
      ws.onmessage = null
      if (ws.readyState === WebSocket.CONNECTING) {
        // Closing a CONNECTING socket logs a browser warning — defer until open
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