import { ref, onMounted, onUnmounted } from 'vue'

export function useWebSocket(url: string | null) {
  const ws = ref<WebSocket | null>(null)
  const lastMessage = ref<unknown>(null)
  const isConnected = ref(false)
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let manualClose = false

  function connect() {
    if (!url) return

    const token = localStorage.getItem('grunt_token')
    const sep = url.includes('?') ? '&' : '?'
    const fullUrl = url.startsWith('ws')
      ? url
      : `ws://localhost:8000${url}${token ? `${sep}token=${encodeURIComponent(token)}` : ''}`

    ws.value = new WebSocket(fullUrl)

    ws.value.onopen = () => {
      isConnected.value = true
    }

    ws.value.onclose = () => {
      isConnected.value = false
      if (!manualClose) {
        reconnectTimer = setTimeout(connect, 3000)
      }
    }

    ws.value.onerror = () => {
      // close will fire after error
    }

    ws.value.onmessage = (e) => {
      try { lastMessage.value = JSON.parse(e.data) }
      catch { lastMessage.value = e.data }
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

  return { lastMessage, isConnected, send }
}
