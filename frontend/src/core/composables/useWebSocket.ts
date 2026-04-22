import { onUnmounted, watch, type MaybeRefOrGetter, toValue } from 'vue'

import { WebSocketChannel } from '@/core/ws/WebSocketChannel'

export function useWebSocket(urlSource: MaybeRefOrGetter<string | null>) {
  const channel = new WebSocketChannel({
    url: toValue(urlSource),
    includeAuthToken: true,
  })

  watch(() => toValue(urlSource), (newUrl) => {
    channel.setUrl(newUrl)
    if (newUrl) {
      channel.connect()
    }
  }, { immediate: true })

  onUnmounted(() => {
    channel.destroy()
  })

  return {
    lastMessage: channel.lastMessage,
    isConnected: channel.isConnected,
    send: (data: unknown) => channel.send(data),
    onEvent: (eventName: string, handler: (data: unknown) => void) => channel.on(eventName, handler),
  }
}
