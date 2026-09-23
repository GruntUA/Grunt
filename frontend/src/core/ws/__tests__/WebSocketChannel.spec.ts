import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'

import { WebSocketChannel, openChannelCount } from '@/core/ws/WebSocketChannel'

class MockWebSocket {
  static instances: MockWebSocket[] = []
  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3

  readonly url: string
  readyState = MockWebSocket.CONNECTING
  onopen: (() => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  sent: string[] = []

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  send(data: string) {
    this.sent.push(data)
  }

  close() {
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.()
  }

  open() {
    this.readyState = MockWebSocket.OPEN
    this.onopen?.()
  }

  message(data: unknown) {
    this.onmessage?.({ data: typeof data === 'string' ? data : JSON.stringify(data) })
  }

  serverClose() {
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.()
  }
}

describe('WebSocketChannel', () => {
  const originalWebSocket = globalThis.WebSocket

  beforeEach(() => {
    vi.useFakeTimers()
    MockWebSocket.instances = []
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    localStorage.setItem('grunt_token', 'test-token')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
    localStorage.clear()
    globalThis.WebSocket = originalWebSocket
  })

  it('appends auth token for relative authenticated URLs', () => {
    const channel = new WebSocketChannel({ url: '/api/v1/ws/user', includeAuthToken: true })

    channel.connect()

    expect(MockWebSocket.instances[0]?.url).toContain('/api/v1/ws/user?token=test-token')
  })

  it('counts open channels per URL for the health report', () => {
    const a = new WebSocketChannel({ url: '/api/v1/ws/user' })
    const b = new WebSocketChannel({ url: '/api/v1/ws/site' })
    a.connect()
    b.connect()
    expect(openChannelCount('/api/v1/ws/user')).toBe(0) // still connecting

    MockWebSocket.instances[0]!.open()
    MockWebSocket.instances[1]!.open()
    expect(openChannelCount('/api/v1/ws/user')).toBe(1)

    MockWebSocket.instances[0]!.serverClose()
    expect(openChannelCount('/api/v1/ws/user')).toBe(0)
    b.destroy()
    expect(openChannelCount('/api/v1/ws/site')).toBe(0)
  })

  it('dispatches named events to listeners', () => {
    const channel = new WebSocketChannel({ url: '/api/v1/ws/user', includeAuthToken: true })
    const handler = vi.fn()

    channel.on('doc_change', handler)
    channel.connect()

    const socket = MockWebSocket.instances[0]
    socket.open()
    socket.message({ event: 'doc_change', data: { id: 'DOC-1' } })

    expect(channel.isConnected.value).toBe(true)
    expect(channel.lastMessage.value).toEqual({ event: 'doc_change', data: { id: 'DOC-1' } })
    expect(handler).toHaveBeenCalledWith({ id: 'DOC-1' })
  })

  it('sends keepalive pings and reconnects after server close', () => {
    const channel = new WebSocketChannel({
      url: '/api/v1/ws/public/site',
      includeAuthToken: false,
      pingIntervalMs: 30_000,
      reconnectDelayMs: 3000,
    })

    channel.connect()

    const firstSocket = MockWebSocket.instances[0]
    firstSocket.open()

    vi.advanceTimersByTime(30_000)
    expect(firstSocket.sent).toContain(JSON.stringify({ action: 'ping' }))

    firstSocket.serverClose()
    vi.advanceTimersByTime(3000)

    expect(MockWebSocket.instances).toHaveLength(2)
    expect(MockWebSocket.instances[1]?.url).toContain('/api/v1/ws/public/site')
  })
})