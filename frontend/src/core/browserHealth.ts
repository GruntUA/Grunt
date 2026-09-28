/**
 * Browser half of the «Стан системи» report — the checks only this browser
 * can answer: is the service worker installed and in control, is the app
 * shell fully pre-cached, do API responses land in the offline cache, what
 * is waiting in the offline queue, how much storage is left.
 *
 * Rows use the same shape as the server checks (grunt/monitoring/health.py),
 * so both render in the same SystemHealthCheck table.
 */
import client from '@/core/api/client'
import { queue, refreshQueue } from '@/core/composables/useOfflineQueue'
import { isOnline, serverReachable } from '@/core/composables/useNetworkStatus'
import { openChannelCount } from '@/core/ws/WebSocketChannel'
import i18n from '@/plugins/i18n'

const t = (key: string): string => i18n.global.t(key)

export type HealthStatus = 'OK' | 'Warning' | 'Error' | 'Info'

export interface HealthRow {
  category: string
  check: string
  status: HealthStatus
  value: string
  hint: string
}

// Must match public/sw.js.
export const SHELL_CACHE_PREFIX = 'grunt-shell-'
export const API_CACHE = 'grunt-api-v1'
const SHELL_KEY = '/__offline_shell__'
const PROBE_URL = '/api/v1/method/grunt.auth.doctypes.User.user.whoami'

const OFFLINE = 'Offline mode'
const NETWORK = 'Network'
const STORAGE = 'Browser storage'
const BROWSER = 'Browser'
const REALTIME = 'WebSockets'

const WS_TIMEOUT_MS = 5000
const ECHO_WAIT_MS = 2500
const ECHO_EVENT = 'health_echo' // grunt/monitoring/health.py

function row(category: string, check: string, status: HealthStatus, value: unknown = '', hint = ''): HealthRow {
  return { category: t(category), check: t(check), status, value: value == null ? '' : t(String(value)), hint: hint ? t(hint) : '' }
}

export function humanSize(bytes: number): string {
  const units = ['B', 'KB', 'MB', 'GB']
  let n = bytes
  for (const unit of units) {
    if (n < 1024) return unit === 'B' ? `${n.toFixed(0)} ${t(unit)}` : `${n.toFixed(1)} ${t(unit)}`
    n /= 1024
  }
  return `${n.toFixed(1)} ${t('TB')}`
}

async function serviceWorkerChecks(): Promise<HealthRow[]> {
  if (!import.meta.env.PROD) {
    return [row(OFFLINE, 'Build', 'Warning', 'development mode',
      'In Vite dev the service worker is not registered — offline works only in a production build.')]
  }
  if (!window.isSecureContext) {
    return [row(OFFLINE, 'Secure connection', 'Error', location.protocol,
      'The service worker works only over HTTPS (or localhost).')]
  }
  if (!('serviceWorker' in navigator)) {
    return [row(OFFLINE, 'Service worker', 'Error', 'not supported', 'The browser does not support offline mode.')]
  }
  const reg = await navigator.serviceWorker.getRegistration()
  if (!reg?.active) {
    return [row(OFFLINE, 'Service worker', 'Error', reg ? 'installing' : 'not registered',
      'Reload the page; if that does not help, check that the server serves /sw.js.')]
  }
  return [
    row(OFFLINE, 'Service worker', 'OK', `${t('active')} (${new URL(reg.active.scriptURL).pathname})`),
    navigator.serviceWorker.controller
      ? row(OFFLINE, 'Controls the page', 'OK', 'yes')
      : row(OFFLINE, 'Controls the page', 'Warning', 'no',
          'The page was opened before the service worker was installed — reload it.'),
  ]
}

async function cacheChecks(): Promise<HealthRow[]> {
  if (!('caches' in window)) return [row(OFFLINE, 'Cache Storage', 'Error', 'unavailable')]
  const names = await caches.keys()
  const shellName = names.find((n) => n.startsWith(SHELL_CACHE_PREFIX))
  const rows: HealthRow[] = []

  if (!shellName) {
    rows.push(row(OFFLINE, 'App cache', import.meta.env.PROD ? 'Error' : 'Info', 'empty',
      'App files are not cached — pages will not open without the network.'))
  } else {
    const shell = await caches.open(shellName)
    const cached = new Set((await shell.keys()).map((r) => new URL(r.url).pathname))
    let manifest: string[] = []
    try {
      const res = await fetch('/precache-manifest.json', { cache: 'no-store' })
      if (res.ok) manifest = await res.json()
    } catch {
      /* offline right now — compare against what is cached */
    }
    const missing = manifest.filter((u) => !cached.has(u))
    rows.push(missing.length
      ? row(OFFLINE, 'App cache', 'Warning', t('{n} files, {missing} missing').replace('{n}', String(cached.size)).replace('{missing}', String(missing.length)),
          t('Not cached, e.g.: {files}. Reload the page while online.').replace('{files}', missing.slice(0, 3).join(', ')))
      : row(OFFLINE, 'App cache', 'OK', `${t('{n} files').replace('{n}', String(cached.size))} (${shellName})`))
    rows.push(await shell.match(SHELL_KEY)
      ? row(OFFLINE, 'Offline page', 'OK', 'saved')
      : row(OFFLINE, 'Offline page', 'Warning', 'missing',
          'The shell is cached after the first page load with the network.'))
  }

  const api = names.includes(API_CACHE) ? await caches.open(API_CACHE) : null
  const entries = api ? (await api.keys()).length : 0
  rows.push(row(OFFLINE, 'Data saved for offline', entries ? 'OK' : 'Info', t('{n} API responses').replace('{n}', String(entries)),
    entries ? '' : 'Open the lists and documents you need while online — they will become available offline.'))
  return rows
}

/** Real round trip: the probe must reach the server and land in the offline cache. */
async function probeChecks(): Promise<HealthRow[]> {
  const started = performance.now()
  try {
    const res = await client.get(PROBE_URL)
    const ms = Math.round(performance.now() - started)
    const fromCache = res.headers['x-grunt-offline'] === '1'
    const rows = [fromCache
      ? row(NETWORK, 'Server', 'Error', 'unavailable', 'The response came from the offline cache.')
      : row(NETWORK, 'Server', ms < 1000 ? 'OK' : 'Warning', `${ms} ${t('ms')}`)]
    if (import.meta.env.PROD && navigator.serviceWorker?.controller && !fromCache) {
      const stored = await caches.match(new URL(PROBE_URL, location.origin).href, { cacheName: API_CACHE })
      rows.push(stored
        ? row(OFFLINE, 'Response caching', 'OK', 'working')
        : row(OFFLINE, 'Response caching', 'Error', 'not working',
            'The service worker did not cache the API response — offline data will not appear.'))
    }
    return rows
  } catch {
    return [row(NETWORK, 'Server', 'Error', 'unavailable')]
  }
}

async function queueChecks(): Promise<HealthRow[]> {
  if (!('indexedDB' in window)) return [row(OFFLINE, 'Change queue', 'Error', 'IndexedDB unavailable')]
  await refreshQueue()
  const count = (s: string) => queue.value.filter((c) => c.status === s).length
  const pending = count('pending')
  const conflict = count('conflict')
  const failed = count('failed')
  const rows = [row(OFFLINE, 'Unsynced changes', pending ? 'Warning' : 'OK', pending,
    pending ? 'They will be sent automatically once the server is reachable.' : '')]
  if (conflict || failed) {
    rows.push(row(OFFLINE, 'Conflicts and rejected changes', 'Warning', t('{conflicts} conflicts, {failed} rejected').replace('{conflicts}', String(conflict)).replace('{failed}', String(failed)),
      'Open «Unsynced changes» at the bottom of the screen and resolve each one.'))
  }
  return rows
}

function networkChecks(): HealthRow[] {
  const conn = (navigator as Navigator & { connection?: { effectiveType?: string; saveData?: boolean } }).connection
  return [
    row(NETWORK, 'Browser network', isOnline.value ? 'OK' : 'Warning', isOnline.value ? 'online' : 'offline'),
    row(NETWORK, 'Server connection', serverReachable.value ? 'OK' : 'Warning',
      serverReachable.value ? 'yes' : 'lost'),
    ...(conn?.effectiveType ? [row(NETWORK, 'Connection type', 'Info', conn.effectiveType + (conn.saveData ? `, ${t('data saver')}` : ''))] : []),
  ]
}

async function storageChecks(): Promise<HealthRow[]> {
  if (!navigator.storage?.estimate) return [row(STORAGE, 'Quota', 'Info', 'unknown')]
  const { usage = 0, quota = 0 } = await navigator.storage.estimate()
  const free = quota ? 1 - usage / quota : 1
  const persisted = navigator.storage.persisted ? await navigator.storage.persisted() : false
  return [
    row(STORAGE, 'Used', free > 0.1 ? 'OK' : 'Warning', `${humanSize(usage)} / ${humanSize(quota)}`,
      free > 0.1 ? '' : 'Low on space — the browser may delete the offline cache.'),
    row(STORAGE, 'Persistent storage', persisted ? 'OK' : 'Info', persisted ? 'yes' : 'no',
      persisted ? '' : 'The browser may clear offline data when space runs low. The «Persist storage» button asks it not to.'),
  ]
}

/** Open a test socket; resolves once it is open, rejects with the close code. */
function openSocket(url: string): Promise<WebSocket> {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(url)
    const timer = setTimeout(() => { ws.close(); reject(new Error('timeout')) }, WS_TIMEOUT_MS)
    ws.onopen = () => { clearTimeout(timer); resolve(ws) }
    ws.onclose = (e) => { clearTimeout(timer); reject(new Error(`code ${e.code}`)) }
  })
}

/** Count matching messages for up to `ms`; with `first`, stop at the first one. */
function waitFor(
  ws: WebSocket,
  match: (msg: Record<string, any>) => boolean,
  ms: number,
  first = false,
): Promise<number> {
  return new Promise((resolve) => {
    let hits = 0
    const done = () => { clearTimeout(timer); ws.removeEventListener('message', onMessage); resolve(hits) }
    const onMessage = (e: MessageEvent) => {
      try {
        if (match(JSON.parse(e.data))) hits++
      } catch { /* not JSON */ }
      if (first && hits) done()
    }
    const timer = setTimeout(done, ms)
    ws.addEventListener('message', onMessage)
  })
}

/**
 * A real round trip on a separate test socket: connect to the user channel,
 * ping → pong, then ask the server to push an event to this user and count
 * how many copies arrive (exactly one is right — two means double delivery).
 */
async function realtimeChecks(): Promise<HealthRow[]> {
  const rows = [openChannelCount('/api/v1/ws/user')
    ? row(REALTIME, 'App realtime', 'OK', 'connected')
    : row(REALTIME, 'App realtime', 'Warning', 'not connected',
        'Notifications and document updates will not arrive live.')]
  if (!('WebSocket' in window)) return [...rows, row(REALTIME, 'Test connection', 'Error', 'not supported')]

  const token = localStorage.getItem('grunt_token') ?? ''
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
  const url = `${proto}//${location.host}/api/v1/ws/user?token=${encodeURIComponent(token)}`
  const started = performance.now()
  let ws: WebSocket
  try {
    ws = await openSocket(url)
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e)
    return [...rows, row(REALTIME, 'Test connection', 'Error', msg === 'code 4001' ? 'token rejected' : msg,
      'Check that the proxy (nginx/Cloudflare) passes WebSocket through on /api/v1/ws/.')]
  }
  try {
    rows.push(row(REALTIME, 'Test connection', 'OK', t('opened in {n} ms').replace('{n}', String(Math.round(performance.now() - started)))))

    const pingAt = performance.now()
    const pong = waitFor(ws, (m) => m.event === 'pong', 2000, true)
    ws.send(JSON.stringify({ action: 'ping' }))
    rows.push(await pong
      ? row(REALTIME, 'Ping → pong', 'OK', `${Math.round(performance.now() - pingAt)} ${t('ms')}`)
      : row(REALTIME, 'Ping → pong', 'Error', 'no response'))

    const nonce = Math.random().toString(36).slice(2)
    const echoes = waitFor(ws, (m) => m.event === ECHO_EVENT && m.data?.nonce === nonce, ECHO_WAIT_MS)
    await client.post('/api/v1/method/grunt.monitoring.health.ws_echo', { nonce })
    const copies = await echoes
    rows.push(copies === 1
      ? row(REALTIME, 'Server delivery', 'OK', 'exactly one copy')
      : copies === 0
        ? row(REALTIME, 'Server delivery', 'Error', 'not delivered',
            'The server sent an event but the browser did not receive it — check the Redis relay.')
        : row(REALTIME, 'Server delivery', 'Warning', t('{n} copies').replace('{n}', String(copies)),
            'Each message arrives several times — notifications are duplicated.'))
  } finally {
    ws.close()
  }
  return rows
}

function browserChecks(): HealthRow[] {
  const permission = 'Notification' in window ? Notification.permission : 'unsupported'
  const labels: Record<string, string> = { granted: 'allowed', denied: 'denied', default: 'not requested', unsupported: 'not supported' }
  return [
    row(BROWSER, 'Browser', 'Info', navigator.userAgent.replace(/^Mozilla\/5\.0 /, '')),
    row(BROWSER, 'Push notifications', permission === 'granted' ? 'OK' : 'Info', labels[permission] ?? permission),
  ]
}

async function safe(category: string, name: string, fn: () => Promise<HealthRow[]> | HealthRow[]): Promise<HealthRow[]> {
  try {
    return await fn()
  } catch (e) {
    return [row(category, name, 'Error', 'check failed', e instanceof Error ? e.message : String(e))]
  }
}

/** Run every browser check; never throws. */
export async function diagnoseBrowser(): Promise<HealthRow[]> {
  const groups = await Promise.all([
    safe(OFFLINE, 'Service worker', serviceWorkerChecks),
    safe(OFFLINE, 'Cache', cacheChecks),
    safe(NETWORK, 'Server', probeChecks),
    safe(OFFLINE, 'Change queue', queueChecks),
    safe(NETWORK, 'Network', networkChecks),
    safe(REALTIME, 'WebSockets', realtimeChecks),
    safe(STORAGE, 'Storage', storageChecks),
    safe(BROWSER, 'Browser', browserChecks),
  ])
  return groups.flat()
}

/** Ask the browser not to evict offline data under storage pressure. */
export async function persistStorage(): Promise<boolean> {
  return navigator.storage?.persist ? navigator.storage.persist() : false
}
