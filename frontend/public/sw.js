// Service Worker — Web Push only, no precaching
self.addEventListener('install', () => self.skipWaiting())
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()))

self.addEventListener('push', e => {
  if (!e.data) return
  let data = {}
  try { data = e.data.json() } catch { data = { title: e.data.text() } }

  const title = data.title || 'Grunt'
  const options = {
    body: data.body || '',
    icon: data.icon || '/assets/logo.png',
    badge: data.badge || '/assets/logo.png',
    data: data.url ? { url: data.url } : {},
  }
  e.waitUntil(self.registration.showNotification(title, options))
})

self.addEventListener('notificationclick', e => {
  e.notification.close()
  const url = e.notification.data?.url
  if (!url) return
  e.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(clients => {
      const match = clients.find(c => c.url === url && 'focus' in c)
      if (match) return match.focus()
      return self.clients.openWindow(url)
    })
  )
})
