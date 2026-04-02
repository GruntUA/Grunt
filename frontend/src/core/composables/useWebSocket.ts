import { ref, onMounted, onUnmounted } from 'vue'

type EventHandler = (data: unknown) => void

export function useWebSocket(url: string | null) {
  const ws = ref<WebSocket | null>(null)
  const lastMessage = ref<unknown>(null)
  const isConnected = ref(false)
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let manualClose = false
  const eventHandlers = new Map<string, EventHandler[]>()

  function onEvent(eventName: string, handler: EventHandler) {
    const handlers = eventHandlers.get(eventName) ?? []
    handlers.push(handler)
    eventHandlers.set(eventName, handlers)
  }

  function connect() {
    if (!url) return

    const token = localStorage.getItem('grunt_token')
    const sep = url.includes('?') ? '&' : '?'
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const fullUrl = url.startsWith('ws')
      ? url
      : `${proto}//${location.host}${url}${token ? `${sep}token=${encodeURIComponent(token)}` : ''}`

    console.log(`[WS] connecting to ${fullUrl}`)
    ws.value = new WebSocket(fullUrl)

    ws.value.onopen = () => {
      console.log(`[WS] connected`)
      isConnected.value = true
    }

    ws.value.onclose = (e) => {
      console.log(`[WS] closed: code=${e.code} reason=${e.reason}`)
      isConnected.value = false
      if (!manualClose) {
        reconnectTimer = setTimeout(connect, 3000)
      }
    }

    ws.value.onerror = (e) => {
      console.error('[WS] error', e)
    }

    ws.value.onmessage = (e) => {
      try {
        const parsed = JSON.parse(e.data)
        lastMessage.value = parsed
        // Dispatch to named event handlers
        if (parsed?.event) {
          const handlers = eventHandlers.get(parsed.event) ?? []
          for (const h of handlers) h(parsed.data)
        }
      } catch {
        lastMessage.value = e.data
      }
    }
  }

  function send(data: unknown) {
    if (ws.value?.readyState === WebSocket.OPEN) {
      ws.value.send(JSON.stringify(data))
    }
  }

  onMounted(connect)

  onUnmounted(() => {
    manualClose = true
    if (reconnectTimer) clearTimeout(reconnectTimer)
    ws.value?.close()
  })

  return { lastMessage, isConnected, send, onEvent }
}
