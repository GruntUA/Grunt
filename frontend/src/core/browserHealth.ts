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

export type HealthStatus = 'OK' | 'Warning' | 'Error' | 'Info'

export interface HealthRow {
  category: string
  check: string
  status: HealthStatus
  value: string
  hint: string
}

// Must match public/sw.js.
const SHELL_CACHE_PREFIX = 'grunt-shell-'
const API_CACHE = 'grunt-api-v1'
const SHELL_KEY = '/__offline_shell__'
const PROBE_URL = '/api/v1/method/grunt.auth.doctypes.User.user.whoami'

const OFFLINE = 'Офлайн-режим'
const NETWORK = 'Мережа'
const STORAGE = 'Сховище браузера'
const BROWSER = 'Браузер'
const REALTIME = 'Вебсокети'

const WS_TIMEOUT_MS = 5000
const ECHO_WAIT_MS = 2500
const ECHO_EVENT = 'health_echo' // grunt/monitoring/health.py

function row(category: string, check: string, status: HealthStatus, value: unknown = '', hint = ''): HealthRow {
  return { category, check, status, value: value == null ? '' : String(value), hint }
}

export function humanSize(bytes: number): string {
  const units = ['Б', 'КБ', 'МБ', 'ГБ']
  let n = bytes
  for (const unit of units) {
    if (n < 1024) return unit === 'Б' ? `${n.toFixed(0)} ${unit}` : `${n.toFixed(1)} ${unit}`
    n /= 1024
  }
  return `${n.toFixed(1)} ТБ`
}

async function serviceWorkerChecks(): Promise<HealthRow[]> {
  if (!import.meta.env.PROD) {
    return [row(OFFLINE, 'Збірка', 'Warning', 'режим розробки',
      'У Vite dev service worker не реєструється — офлайн працює лише в production-збірці.')]
  }
  if (!window.isSecureContext) {
    return [row(OFFLINE, 'Безпечне з\'єднання', 'Error', location.protocol,
      'Service worker працює лише через HTTPS (або localhost).')]
  }
  if (!('serviceWorker' in navigator)) {
    return [row(OFFLINE, 'Service worker', 'Error', 'не підтримується', 'Браузер не підтримує офлайн-режим.')]
  }
  const reg = await navigator.serviceWorker.getRegistration()
  if (!reg?.active) {
    return [row(OFFLINE, 'Service worker', 'Error', reg ? 'встановлюється' : 'не зареєстрований',
      'Перезавантажте сторінку; якщо не допомагає — перевірте, що /sw.js віддається сервером.')]
  }
  return [
    row(OFFLINE, 'Service worker', 'OK', `активний (${new URL(reg.active.scriptURL).pathname})`),
    navigator.serviceWorker.controller
      ? row(OFFLINE, 'Керує сторінкою', 'OK', 'так')
      : row(OFFLINE, 'Керує сторінкою', 'Warning', 'ні',
          'Сторінку відкрито до встановлення service worker — перезавантажте її.'),
  ]
}

async function cacheChecks(): Promise<HealthRow[]> {
  if (!('caches' in window)) return [row(OFFLINE, 'Cache Storage', 'Error', 'недоступне')]
  const names = await caches.keys()
  const shellName = names.find((n) => n.startsWith(SHELL_CACHE_PREFIX))
  const rows: HealthRow[] = []

  if (!shellName) {
    rows.push(row(OFFLINE, 'Кеш застосунку', import.meta.env.PROD ? 'Error' : 'Info', 'порожній',
      'Файли застосунку не збережені — без мережі сторінки не відкриються.'))
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
      ? row(OFFLINE, 'Кеш застосунку', 'Warning', `${cached.size} файлів, бракує ${missing.length}`,
          `Не збережено, напр.: ${missing.slice(0, 3).join(', ')}. Перезавантажте сторінку з мережею.`)
      : row(OFFLINE, 'Кеш застосунку', 'OK', `${cached.size} файлів (${shellName})`))
    rows.push(await shell.match(SHELL_KEY)
      ? row(OFFLINE, 'Офлайн-сторінка', 'OK', 'збережена')
      : row(OFFLINE, 'Офлайн-сторінка', 'Warning', 'відсутня',
          'Оболонка зберігається після першого відкриття сторінки з мережею.'))
  }

  const api = names.includes(API_CACHE) ? await caches.open(API_CACHE) : null
  const entries = api ? (await api.keys()).length : 0
  rows.push(row(OFFLINE, 'Збережені дані для офлайну', entries ? 'OK' : 'Info', `${entries} відповідей API`,
    entries ? '' : 'Відкрийте потрібні списки й документи з мережею — вони стануть доступні офлайн.'))
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
      ? row(NETWORK, 'Сервер', 'Error', 'недоступний', 'Відповідь прийшла з офлайн-кешу.')
      : row(NETWORK, 'Сервер', ms < 1000 ? 'OK' : 'Warning', `${ms} мс`)]
    if (import.meta.env.PROD && navigator.serviceWorker?.controller && !fromCache) {
      const stored = await caches.match(new URL(PROBE_URL, location.origin).href, { cacheName: API_CACHE })
      rows.push(stored
        ? row(OFFLINE, 'Кешування відповідей', 'OK', 'працює')
        : row(OFFLINE, 'Кешування відповідей', 'Error', 'не працює',
            'Service worker не зберіг відповідь API — офлайн дані не з\'являться.'))
    }
    return rows
  } catch {
    return [row(NETWORK, 'Сервер', 'Error', 'недоступний')]
  }
}

async function queueChecks(): Promise<HealthRow[]> {
  if (!('indexedDB' in window)) return [row(OFFLINE, 'Черга змін', 'Error', 'IndexedDB недоступна')]
  await refreshQueue()
  const count = (s: string) => queue.value.filter((c) => c.status === s).length
  const pending = count('pending')
  const conflict = count('conflict')
  const failed = count('failed')
  const rows = [row(OFFLINE, 'Несинхронізовані зміни', pending ? 'Warning' : 'OK', pending,
    pending ? 'Надішлються автоматично, щойно сервер стане доступний.' : '')]
  if (conflict || failed) {
    rows.push(row(OFFLINE, 'Конфлікти й відхилені зміни', 'Warning', `${conflict} конфліктів, ${failed} відхилено`,
      'Відкрийте «Несинхронізовані зміни» внизу екрана й вирішіть кожну.'))
  }
  return rows
}

function networkChecks(): HealthRow[] {
  const conn = (navigator as Navigator & { connection?: { effectiveType?: string; saveData?: boolean } }).connection
  return [
    row(NETWORK, 'Мережа браузера', isOnline.value ? 'OK' : 'Warning', isOnline.value ? 'онлайн' : 'офлайн'),
    row(NETWORK, 'З\'єднання з сервером', serverReachable.value ? 'OK' : 'Warning',
      serverReachable.value ? 'є' : 'втрачено'),
    ...(conn?.effectiveType ? [row(NETWORK, 'Тип з\'єднання', 'Info', conn.effectiveType + (conn.saveData ? ', економія трафіку' : ''))] : []),
  ]
}

async function storageChecks(): Promise<HealthRow[]> {
  if (!navigator.storage?.estimate) return [row(STORAGE, 'Квота', 'Info', 'невідомо')]
  const { usage = 0, quota = 0 } = await navigator.storage.estimate()
  const free = quota ? 1 - usage / quota : 1
  const persisted = navigator.storage.persisted ? await navigator.storage.persisted() : false
  return [
    row(STORAGE, 'Використано', free > 0.1 ? 'OK' : 'Warning', `${humanSize(usage)} з ${humanSize(quota)}`,
      free > 0.1 ? '' : 'Місця мало — браузер може видалити офлайн-кеш.'),
    row(STORAGE, 'Постійне сховище', persisted ? 'OK' : 'Info', persisted ? 'так' : 'ні',
      persisted ? '' : 'Браузер може очистити офлайн-дані при нестачі місця. Кнопка «Закріпити сховище» просить його цього не робити.'),
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
    ? row(REALTIME, 'Realtime застосунку', 'OK', 'підключено')
    : row(REALTIME, 'Realtime застосунку', 'Warning', 'не підключено',
        'Сповіщення й оновлення документів не приходитимуть наживо.')]
  if (!('WebSocket' in window)) return [...rows, row(REALTIME, 'Тестове з\'єднання', 'Error', 'не підтримується')]

  const token = localStorage.getItem('grunt_token') ?? ''
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
  const url = `${proto}//${location.host}/api/v1/ws/user?token=${encodeURIComponent(token)}`
  const started = performance.now()
  let ws: WebSocket
  try {
    ws = await openSocket(url)
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e)
    return [...rows, row(REALTIME, 'Тестове з\'єднання', 'Error', msg === 'code 4001' ? 'токен не прийнято' : msg,
      'Перевірте, що проксі (nginx/Cloudflare) пропускає WebSocket на /api/v1/ws/.')]
  }
  try {
    rows.push(row(REALTIME, 'Тестове з\'єднання', 'OK', `відкрито за ${Math.round(performance.now() - started)} мс`))

    const pingAt = performance.now()
    const pong = waitFor(ws, (m) => m.event === 'pong', 2000, true)
    ws.send(JSON.stringify({ action: 'ping' }))
    rows.push(await pong
      ? row(REALTIME, 'Ping → pong', 'OK', `${Math.round(performance.now() - pingAt)} мс`)
      : row(REALTIME, 'Ping → pong', 'Error', 'немає відповіді'))

    const nonce = Math.random().toString(36).slice(2)
    const echoes = waitFor(ws, (m) => m.event === ECHO_EVENT && m.data?.nonce === nonce, ECHO_WAIT_MS)
    await client.post('/api/v1/method/grunt.monitoring.health.ws_echo', { nonce })
    const copies = await echoes
    rows.push(copies === 1
      ? row(REALTIME, 'Доставка з сервера', 'OK', 'рівно одна копія')
      : copies === 0
        ? row(REALTIME, 'Доставка з сервера', 'Error', 'не дійшло',
            'Сервер надіслав подію, але браузер її не отримав — перевірте ретрансляцію через Redis.')
        : row(REALTIME, 'Доставка з сервера', 'Warning', `${copies} копії`,
            'Кожне повідомлення приходить кілька разів — сповіщення дублюються.'))
  } finally {
    ws.close()
  }
  return rows
}

function browserChecks(): HealthRow[] {
  const permission = 'Notification' in window ? Notification.permission : 'unsupported'
  const labels: Record<string, string> = { granted: 'дозволено', denied: 'заборонено', default: 'не запитано', unsupported: 'не підтримується' }
  return [
    row(BROWSER, 'Браузер', 'Info', navigator.userAgent.replace(/^Mozilla\/5\.0 /, '')),
    row(BROWSER, 'Push-сповіщення', permission === 'granted' ? 'OK' : 'Info', labels[permission] ?? permission),
  ]
}

async function safe(category: string, name: string, fn: () => Promise<HealthRow[]> | HealthRow[]): Promise<HealthRow[]> {
  try {
    return await fn()
  } catch (e) {
    return [row(category, name, 'Error', 'перевірка впала', e instanceof Error ? e.message : String(e))]
  }
}

/** Run every browser check; never throws. */
export async function diagnoseBrowser(): Promise<HealthRow[]> {
  const groups = await Promise.all([
    safe(OFFLINE, 'Service worker', serviceWorkerChecks),
    safe(OFFLINE, 'Кеш', cacheChecks),
    safe(NETWORK, 'Сервер', probeChecks),
    safe(OFFLINE, 'Черга змін', queueChecks),
    safe(NETWORK, 'Мережа', networkChecks),
    safe(REALTIME, 'Вебсокети', realtimeChecks),
    safe(STORAGE, 'Сховище', storageChecks),
    safe(BROWSER, 'Браузер', browserChecks),
  ])
  return groups.flat()
}

/** Ask the browser not to evict offline data under storage pressure. */
export async function persistStorage(): Promise<boolean> {
  return navigator.storage?.persist ? navigator.storage.persist() : false
}
