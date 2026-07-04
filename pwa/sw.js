// Minimal service worker: makes the app installable and caches the shell so it
// opens instantly / offline. Analysis itself (POST /api/*) always needs the
// server, so only GETs are cached, network-first.
const CACHE = 'rfa-v1'

self.addEventListener('install', () => self.skipWaiting())
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()))

self.addEventListener('fetch', (e) => {
  if (e.request.method !== 'GET') return // uploads/results go straight to network
  e.respondWith(
    fetch(e.request)
      .then((res) => {
        const copy = res.clone()
        caches.open(CACHE).then((c) => c.put(e.request, copy)).catch(() => {})
        return res
      })
      .catch(() => caches.match(e.request)),
  )
})
