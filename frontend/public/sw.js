// Minimal offline-first service worker for the app shell.
// API calls are NOT cached here — api.js owns write queueing, and stale
// reads are worse than a clear offline indicator for school data.
const CACHE = 'cbc-shell-v1'
const SHELL = ['/', '/manifest.webmanifest', '/icon.svg']

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)))
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))),
    ),
  )
  self.clients.claim()
})

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url)
  // Only same-origin http(s) GETs are cacheable. Browser extensions issue
  // chrome-extension:// requests through the page; the Cache API rejects those
  // schemes, which is where the noisy "Request scheme is unsupported" errors
  // came from. Skip anything that isn't ours to cache.
  if (
    event.request.method !== 'GET' ||
    url.origin !== self.location.origin ||
    !url.protocol.startsWith('http') ||
    url.pathname.startsWith('/api')
  ) {
    return
  }

  // Network first, cache fallback: fresh assets when online, shell when not.
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        // Only cache complete, basic (same-origin) responses.
        if (response.ok && response.type === 'basic') {
          const copy = response.clone()
          caches.open(CACHE).then((cache) => cache.put(event.request, copy))
        }
        return response
      })
      .catch(() =>
        caches.match(event.request).then((hit) => hit || caches.match('/')),
      ),
  )
})
