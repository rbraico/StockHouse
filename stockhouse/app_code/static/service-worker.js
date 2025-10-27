const CACHE_NAME = 'stockhouse-cache-v1';
const urlsToCache = [
  '/',
  '/index',
  '/shopping_list',
  '/static/style.css',
  '/static/script.js',
  '/static/icons/StockHouse_icon-192.png',
  '/static/icons/StockHouse_icon-512.png'
];

// Installazione
self.addEventListener('install', event => {
  console.log('[Service Worker] Install');
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        return cache.addAll(urlsToCache);
      })
  );
});

// Fetch intercettato
self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => {
        return response || fetch(event.request);
      })
  );
});
