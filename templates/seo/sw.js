/* v5: app.js/app.css gained the push-notification toggle; bump the name so
   clients drop the old cached copies. */
const CACHE_NAME = 'yalla-zaker-cache-v5';
const urlsToCache = [
  '/static/css/app.css',
  '/static/js/app.js',
  '/static/icons/icon-192x192.png',
  '/static/icons/icon-512x512.png'
];

self.addEventListener('install', event => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        return cache.addAll(urlsToCache);
      })
  );
});

self.addEventListener('fetch', event => {
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request).catch(error => {
        console.error('Navigation fetch failed:', error);
      })
    );
    return;
  }

  event.respondWith(
    caches.match(event.request)
      .then(response => {
        if (response) {
          return response;
        }
        return fetch(event.request).then(networkResponse => {
          return networkResponse;
        }).catch(error => {
          console.error('Fetch failed; returning offline page instead.', error);
        });
      })
  );
});

self.addEventListener('push', event => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (e) {}
  event.waitUntil(
    self.registration.showNotification(data.title || 'yalla zaker', {
      body: data.body || '',
      icon: '/static/icons/icon-192x192.png',
      badge: '/static/icons/icon-192x192.png',
      tag: 'inactivity-reminder',
      data: { url: data.url || '/dashboard/' }
    })
  );
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const target = new URL(event.notification.data.url, self.location.origin).href;
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(windows => {
      for (const w of windows) {
        if ('focus' in w) return w.navigate(target).then(c => c && c.focus());
      }
      return clients.openWindow(target);
    })
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          if (cacheName !== CACHE_NAME) {
            return caches.delete(cacheName);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});
