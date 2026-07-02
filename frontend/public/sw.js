/* United Exploration ERP — Service Worker
 *
 * Scope: app shell + static assets only.
 *
 * Sensitive data (auth tokens, payslip figures, employee lists, etc.)
 * are NEVER cached. Every /api/* request is network-only.
 *
 * Punches (attendance mark / punch-out) are network-only. When offline
 * the client shows the offline page — we deliberately do NOT queue a
 * punch for later replay because that would fabricate a "location" and
 * "time" the user was not verified at.
 */

const CACHE_VERSION = 'ue-erp-shell-v1';
const OFFLINE_URL = '/offline.html';
const PRECACHE_URLS = [
  '/',
  '/offline.html',
  '/manifest.webmanifest',
  '/icons/icon-192.svg',
  '/icons/icon-512.svg',
  '/icons/icon-maskable-512.svg',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_VERSION).then((cache) => cache.addAll(PRECACHE_URLS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(
      keys.filter((k) => k !== CACHE_VERSION).map((k) => caches.delete(k))
    );
    await self.clients.claim();
  })());
});

function isApiRequest(url) {
  return url.pathname.startsWith('/api/');
}

function isStaticAsset(url) {
  // Vite hashed assets live under /assets/*; icons under /icons/*.
  if (url.pathname.startsWith('/assets/')) return true;
  if (url.pathname.startsWith('/icons/')) return true;
  return /\.(css|js|svg|woff2?|ttf|otf|png|jpg|jpeg|webp|ico)$/i.test(
    url.pathname
  );
}

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // Never touch API — always network. No offline replay of punches, no
  // stale payslip figures. If it fails, it fails and the caller decides.
  if (isApiRequest(url)) return;

  // Navigation: network-first, fall back to cached shell, then offline page.
  if (req.mode === 'navigate') {
    event.respondWith((async () => {
      try {
        const fresh = await fetch(req);
        const cache = await caches.open(CACHE_VERSION);
        cache.put('/', fresh.clone());
        return fresh;
      } catch (_err) {
        const cache = await caches.open(CACHE_VERSION);
        const cachedShell = await cache.match('/');
        if (cachedShell) return cachedShell;
        const offline = await cache.match(OFFLINE_URL);
        return offline || new Response('Offline', { status: 503 });
      }
    })());
    return;
  }

  // Static assets: stale-while-revalidate.
  if (isStaticAsset(url)) {
    event.respondWith((async () => {
      const cache = await caches.open(CACHE_VERSION);
      const cached = await cache.match(req);
      const network = fetch(req).then((res) => {
        if (res && res.status === 200) cache.put(req, res.clone());
        return res;
      }).catch(() => null);
      return cached || (await network) || new Response('', { status: 504 });
    })());
    return;
  }

  // Anything else: passthrough.
});

// Allow the page to trigger an update-and-reload via a message.
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});
