/**
 * Grunt Service Worker — offline app shell, offline reading, Web Push.
 *
 *  - install: pre-caches every built asset listed in /precache-manifest.json
 *    (emitted by the `grunt-precache-manifest` Vite plugin), so pages never
 *    visited online still open offline.
 *  - navigation: network first; the last good HTML is kept as the offline shell.
 *  - GET /api/*: network first, the last good response per URL is the offline
 *    copy (lists, documents, metadata, whoami). Files (get_content) and the
 *    websocket are never cached. The page wipes this cache on logout
 *    (message `clear-user-data`) — it holds one user's data.
 *  - other same-origin GETs (hashed assets, fonts, icons): cache first.
 *
 * Mutations are never touched here — the page's offline queue handles them.
 */

const SHELL_CACHE = 'grunt-shell-v3'
const API_CACHE = 'grunt-api-v1'
const SHELL_KEY = '/__offline_shell__'

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    try {
      const res = await fetch('/precache-manifest.json', { cache: 'no-store' })
      if (res.ok) {
        const urls = await res.json()
        const cache = await caches.open(SHELL_CACHE)
        // One by one — a single missing file must not abort the whole install.
        await Promise.all(urls.map((u) => cache.add(u).catch(() => undefined)))
      }
    } catch {
      /* dev server / no manifest: runtime caching still works */
    }
    await self.skipWaiting()
  })())
})

self.addEventListener('activate', (event) => {
  const keep = new Set([SHELL_CACHE, API_CACHE])
  event.waitUntil(
    caches.keys()
      .then((names) => Promise.all(names.filter((n) => !keep.has(n)).map((n) => caches.delete(n))))
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('message', (event) => {
  if (event.data === 'clear-user-data') event.waitUntil(caches.delete(API_CACHE))
})

self.addEventListener('fetch', (event) => {
  const { request } = event
  const url = new URL(request.url)
  if (request.method !== 'GET' || url.origin !== self.location.origin) return

  if (url.pathname.startsWith('/api/')) {
    if (url.pathname.includes('/ws/') || url.pathname.includes('.get_content')) return
    event.respondWith(networkFirst(request, API_CACHE))
    return
  }

  if (request.mode === 'navigate') {
    event.respondWith(navigation(request))
    return
  }

  event.respondWith(cacheFirst(request, SHELL_CACHE))
})

async function navigation(request) {
  const cache = await caches.open(SHELL_CACHE)
  try {
    const response = await fetch(request)
    if (response.ok && (response.headers.get('content-type') || '').includes('text/html')) {
      cache.put(SHELL_KEY, response.clone())
    }
    return response
  } catch {
    const shell = await cache.match(SHELL_KEY)
    return shell ?? new Response('Немає з’єднання', { status: 503, headers: { 'content-type': 'text/plain; charset=utf-8' } })
  }
}

async function networkFirst(request, cacheName) {
  const cache = await caches.open(cacheName)
  try {
    const response = await fetch(request)
    if (response.ok) cache.put(request, response.clone())
    return response
  } catch (err) {
    const cached = await cache.match(request)
    if (!cached) throw err
    // Tell the page this is an offline copy (it then knows the server is unreachable).
    const headers = new Headers(cached.headers)
    headers.set('X-Grunt-Offline', '1')
    return new Response(cached.body, { status: cached.status, statusText: cached.statusText, headers })
  }
}

async function cacheFirst(request, cacheName) {
  const cached = await caches.match(request)
  if (cached) return cached
  const response = await fetch(request)
  if (response.ok) {
    const cache = await caches.open(cacheName)
    cache.put(request, response.clone())
  }
  return response
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
    }),
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const url = event.notification.data?.url || '/'
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
      for (const client of list) {
        if (client.url.includes(self.location.origin) && 'focus' in client) {
          client.navigate(url)
          return client.focus()
        }
      }
      return self.clients.openWindow(url)
    }),
  )
})
