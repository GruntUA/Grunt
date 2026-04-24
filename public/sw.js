/**
 * Grunt Service Worker
 *
 * Handles:
 *  - Web Push notifications
 *  - Offline caching (cache-first for assets, stale-while-revalidate for meta API)
 *  - Navigation fallback to /index.html
 */

// ── Cache names ───────────────────────────────────────────────────────────────
const SHELL_CACHE = 'grunt-shell-v2'
const RUNTIME_CACHE = 'grunt-runtime-v2'

// ── Install: pre-cache app shell ──────────────────────────────────────────────
self.addEventListener('install', (event) => {
  event.waitUntil(self.skipWaiting())
})

// ── Activate: clean up old caches ────────────────────────────────────────────
self.addEventListener('activate', (event) => {
  const keep = new Set([SHELL_CACHE, RUNTIME_CACHE])
  event.waitUntil(
    caches.keys()
      .then((names) => Promise.all(
        names
          .filter((n) => !keep.has(n))
          .map((n) => caches.delete(n))
      ))
      .then(() => clients.claim())
  )
})

// ── Fetch: routing strategy ───────────────────────────────────────────────────
self.addEventListener('fetch', (event) => {
  const { request } = event
  const url = new URL(request.url)

  // Only handle same-origin GET requests
  if (request.method !== 'GET' || url.origin !== self.location.origin) return

  // ① API — stale-while-revalidate for DocType metadata; skip all other /api/
  if (url.pathname.startsWith('/api/')) {
    if (url.pathname.includes('/meta/doctypes')) {
      event.respondWith(_staleWhileRevalidate(request, RUNTIME_CACHE))
    }
    // All other API calls: network-only (mutations, auth, etc.)
    return
  }

  // ② Navigation (HTML) — network first, fall back to /index.html
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request).catch(() =>
        caches.match('/index.html').then((r) => r ?? fetch('/index.html'))
      )
    )
    return
  }

  // ③ Static assets — cache first
  event.respondWith(_cacheFirst(request, SHELL_CACHE))
})

// ── Helpers ───────────────────────────────────────────────────────────────────

async function _cacheFirst(request, cacheName) {
  const cached = await caches.match(request)
  if (cached) return cached
  const response = await fetch(request)
  if (response.ok) {
    const cache = await caches.open(cacheName)
    cache.put(request, response.clone())
  }
  return response
}

async function _staleWhileRevalidate(request, cacheName) {
  const cache = await caches.open(cacheName)
  const cached = await cache.match(request)
  const fetchPromise = fetch(request).then((response) => {
    if (response.ok) cache.put(request, response.clone())
    return response
  })
  return cached ?? fetchPromise
}

// ── Push notifications ────────────────────────────────────────────────────────
self.addEventListener('push', (event) => {
  if (!event.data) return

  let payload = { title: 'Сповіщення', body: '', url: '/' }
  try {
    payload = { ...payload, ...event.data.json() }
  } catch {
    payload.body = event.data.text()
  }

  event.waitUntil(
    self.registration.showNotification(payload.title, {
      body: payload.body,
      icon: '/favicon.ico',
      badge: '/favicon.ico',
      data: { url: payload.url || '/' },
      vibrate: [100, 50, 100],
      requireInteraction: false,
    })
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const url = event.notification.data?.url || '/'
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
      for (const client of list) {
        if (client.url.includes(self.location.origin) && 'focus' in client) {
          client.navigate(url)
          return client.focus()
        }
      }
      return clients.openWindow(url)
    })
  )
})
