/**
 * Browser half of the «Стан системи» report - the checks only this browser
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
import { authProtocols, buildWebSocketUrl, openChannelCount } from '@/core/ws/WebSocketChannel'
import i18n, { N_ } from '@/plugins/i18n'

const t = (key: string, params: Record<string, unknown> = {}): string => i18n.global.t(key, params)

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

const OFFLINE = N_('Offline mode')
const NETWORK = N_('Network')
const STORAGE = N_('Browser storage')
const BROWSER = N_('Browser')
const REALTIME = N_('WebSockets')

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
    return [row(OFFLINE, N_('Build'), 'Warning', N_('development mode'),
      N_('In Vite dev the service worker is not registered — offline works only in a production build.'))]
  }
  if (!window.isSecureContext) {
    return [row(OFFLINE, N_('Secure connection'), 'Error', location.protocol,
      N_('The service worker works only over HTTPS (or localhost).'))]
  }
  if (!('serviceWorker' in navigator)) {
    return [row(OFFLINE, N_('Service worker'), 'Error', N_('not supported'), N_('The browser does not support offline mode.'))]
  }
  const reg = await navigator.serviceWorker.getRegistration()
  if (!reg?.active) {
    return [row(OFFLINE, N_('Service worker'), 'Error', reg ? N_('installing') : N_('not registered'),
      N_('Reload the page; if that does not help, check that the server serves /sw.js.'))]
  }
  return [
    row(OFFLINE, N_('Service worker'), 'OK', `${t('active')} (${new URL(reg.active.scriptURL).pathname})`),
    navigator.serviceWorker.controller
      ? row(OFFLINE, N_('Controls the page'), 'OK', N_('yes'))
      : row(OFFLINE, N_('Controls the page'), 'Warning', N_('no'),
          N_('The page was opened before the service worker was installed — reload it.')),
  ]
}

async function cacheChecks(): Promise<HealthRow[]> {
  if (!('caches' in window)) return [row(OFFLINE, N_('Cache Storage'), 'Error', N_('unavailable'))]
  const names = await caches.keys()
  const shellName = names.find((n) => n.startsWith(SHELL_CACHE_PREFIX))
  const rows: HealthRow[] = []

  if (!shellName) {
    rows.push(row(OFFLINE, N_('App cache'), import.meta.env.PROD ? 'Error' : 'Info', N_('empty'),
      N_('App files are not cached — pages will not open without the network.')))
  } else {
    const shell = await caches.open(shellName)
    const cached = new Set((await shell.keys()).map((r) => new URL(r.url).pathname))
    let manifest: string[] = []
    try {
      const res = await fetch('/precache-manifest.json', { cache: 'no-store' })
      if (res.ok) manifest = await res.json()
    } catch {
      /* offline right now - compare against what is cached */
    }
    const missing = manifest.filter((u) => !cached.has(u))
    rows.push(missing.length
      ? row(OFFLINE, N_('App cache'), 'Warning', t('{n} files, {missing} missing', { n: String(cached.size), missing: String(missing.length) }),
          t('Not cached, e.g.: {files}. Reload the page while online.', { files: missing.slice(0, 3).join(', ') }))
      : row(OFFLINE, N_('App cache'), 'OK', `${t('{n} files', { n: String(cached.size) })} (${shellName})`))
    rows.push(await shell.match(SHELL_KEY)
      ? row(OFFLINE, N_('Offline page'), 'OK', N_('saved'))
      : row(OFFLINE, N_('Offline page'), 'Warning', N_('missing'),
          N_('The shell is cached after the first page load with the network.')))
  }

  const api = names.includes(API_CACHE) ? await caches.open(API_CACHE) : null
  const entries = api ? (await api.keys()).length : 0
  rows.push(row(OFFLINE, N_('Data saved for offline'), entries ? 'OK' : 'Info', t('{n} API responses', { n: String(entries) }),
    entries ? '' : N_('Open the lists and documents you need while online — they will become available offline.')))
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
      ? row(NETWORK, N_('Server'), 'Error', N_('unavailable'), N_('The response came from the offline cache.'))
      : row(NETWORK, N_('Server'), ms < 1000 ? 'OK' : 'Warning', `${ms} ${t('ms')}`)]
    if (import.meta.env.PROD && navigator.serviceWorker?.controller && !fromCache) {
      const stored = await caches.match(new URL(PROBE_URL, location.origin).href, { cacheName: API_CACHE })
      rows.push(stored
        ? row(OFFLINE, N_('Response caching'), 'OK', N_('working'))
        : row(OFFLINE, N_('Response caching'), 'Error', N_('not working'),
            N_('The service worker did not cache the API response — offline data will not appear.')))
    }
    return rows
  } catch {
    return [row(NETWORK, N_('Server'), 'Error', N_('unavailable'))]
  }
}

async function queueChecks(): Promise<HealthRow[]> {
  if (!('indexedDB' in window)) return [row(OFFLINE, N_('Change queue'), 'Error', N_('IndexedDB unavailable'))]
  await refreshQueue()
  const count = (s: string) => queue.value.filter((c) => c.status === s).length
  const pending = count('pending')
  const conflict = count('conflict')
  const failed = count('failed')
  const rows = [row(OFFLINE, N_('Unsynced changes'), pending ? 'Warning' : 'OK', pending,
    pending ? N_('They will be sent automatically once the server is reachable.') : '')]
  if (conflict || failed) {
    rows.push(row(OFFLINE, N_('Conflicts and rejected changes'), 'Warning', t('{conflicts} conflicts, {failed} rejected', { conflicts: String(conflict), failed: String(failed) }),
      N_('Open «Unsynced changes» at the bottom of the screen and resolve each one.')))
  }
  return rows
}

function networkChecks(): HealthRow[] {
  const conn = (navigator as Navigator & { connection?: { effectiveType?: string; saveData?: boolean } }).connection
  return [
    row(NETWORK, N_('Browser network'), isOnline.value ? 'OK' : 'Warning', isOnline.value ? N_('online') : N_('offline')),
    row(NETWORK, N_('Server connection'), serverReachable.value ? 'OK' : 'Warning',
      serverReachable.value ? N_('yes') : N_('lost')),
    ...(conn?.effectiveType ? [row(NETWORK, N_('Connection type'), 'Info', conn.effectiveType + (conn.saveData ? `, ${t('data saver')}` : ''))] : []),
  ]
}

async function storageChecks(): Promise<HealthRow[]> {
  if (!navigator.storage?.estimate) return [row(STORAGE, N_('Quota'), 'Info', N_('unknown'))]
  const { usage = 0, quota = 0 } = await navigator.storage.estimate()
  const free = quota ? 1 - usage / quota : 1
  const persisted = navigator.storage.persisted ? await navigator.storage.persisted() : false
  return [
    row(STORAGE, N_('Used'), free > 0.1 ? 'OK' : 'Warning', `${humanSize(usage)} / ${humanSize(quota)}`,
      free > 0.1 ? '' : N_('Low on space — the browser may delete the offline cache.')),
    row(STORAGE, N_('Persistent storage'), persisted ? 'OK' : 'Info', persisted ? N_('yes') : N_('no'),
      persisted ? '' : N_('The browser may clear offline data when space runs low. The «Persist storage» button asks it not to.')),
  ]
}

/** Open a test socket; resolves once it is open, rejects with the close code. */
function openSocket(url: string): Promise<WebSocket> {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(buildWebSocketUrl(url), authProtocols())
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
 * ping -> pong, then ask the server to push an event to this user and count
 * how many copies arrive (exactly one is right - two means double delivery).
 */
async function realtimeChecks(): Promise<HealthRow[]> {
  const rows = [openChannelCount('/api/v1/ws/user')
    ? row(REALTIME, N_('App realtime'), 'OK', N_('connected'))
    : row(REALTIME, N_('App realtime'), 'Warning', N_('not connected'),
        N_('Notifications and document updates will not arrive live.'))]
  if (!('WebSocket' in window)) return [...rows, row(REALTIME, N_('Test connection'), 'Error', N_('not supported'))]

  const started = performance.now()
  let ws: WebSocket
  try {
    ws = await openSocket('/api/v1/ws/user')
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e)
    return [...rows, row(REALTIME, N_('Test connection'), 'Error', msg === N_('code 4001') ? N_('token rejected') : msg,
      N_('Check that the proxy (nginx/Cloudflare) passes WebSocket through on /api/v1/ws/.'))]
  }
  try {
    rows.push(row(REALTIME, N_('Test connection'), 'OK', t('opened in {n} ms', { n: String(Math.round(performance.now() - started)) })))

    const pingAt = performance.now()
    const pong = waitFor(ws, (m) => m.event === 'pong', 2000, true)
    ws.send(JSON.stringify({ action: 'ping' }))
    rows.push(await pong
      ? row(REALTIME, N_('Ping → pong'), 'OK', `${Math.round(performance.now() - pingAt)} ${t('ms')}`)
      : row(REALTIME, N_('Ping → pong'), 'Error', N_('no response')))

    const nonce = Math.random().toString(36).slice(2)
    const echoes = waitFor(ws, (m) => m.event === ECHO_EVENT && m.data?.nonce === nonce, ECHO_WAIT_MS)
    await client.post('/api/v1/method/grunt.monitoring.health.ws_echo', { nonce })
    const copies = await echoes
    rows.push(copies === 1
      ? row(REALTIME, N_('Server delivery'), 'OK', N_('exactly one copy'))
      : copies === 0
        ? row(REALTIME, N_('Server delivery'), 'Error', N_('not delivered'),
            N_('The server sent an event but the browser did not receive it — check the Redis relay.'))
        : row(REALTIME, N_('Server delivery'), 'Warning', t('{n} copies', { n: String(copies) }),
            N_('Each message arrives several times — notifications are duplicated.')))
  } finally {
    ws.close()
  }
  return rows
}

function browserChecks(): HealthRow[] {
  const permission = 'Notification' in window ? Notification.permission : 'unsupported'
  const labels: Record<string, string> = { granted: N_('allowed'), denied: N_('denied'), default: N_('not requested'), unsupported: 'not supported' }
  return [
    row(BROWSER, N_('Browser'), 'Info', navigator.userAgent.replace(/^Mozilla\/5\.0 /, '')),
    row(BROWSER, N_('Push notifications'), permission === 'granted' ? 'OK' : 'Info', labels[permission] ?? permission),
  ]
}

async function safe(category: string, name: string, fn: () => Promise<HealthRow[]> | HealthRow[]): Promise<HealthRow[]> {
  try {
    return await fn()
  } catch (e) {
    return [row(category, name, 'Error', N_('check failed'), e instanceof Error ? e.message : String(e))]
  }
}

/** Run every browser check; never throws. */
export async function diagnoseBrowser(): Promise<HealthRow[]> {
  const groups = await Promise.all([
    safe(OFFLINE, N_('Service worker'), serviceWorkerChecks),
    safe(OFFLINE, N_('Cache'), cacheChecks),
    safe(NETWORK, N_('Server'), probeChecks),
    safe(OFFLINE, N_('Change queue'), queueChecks),
    safe(NETWORK, N_('Network'), networkChecks),
    safe(REALTIME, N_('WebSockets'), realtimeChecks),
    safe(STORAGE, N_('Storage'), storageChecks),
    safe(BROWSER, N_('Browser'), browserChecks),
  ])
  return groups.flat()
}

/** Ask the browser not to evict offline data under storage pressure. */
export async function persistStorage(): Promise<boolean> {
  return navigator.storage?.persist ? navigator.storage.persist() : false
}
