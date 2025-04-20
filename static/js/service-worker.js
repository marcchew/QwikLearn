// Service Worker for QwikLearn
const CACHE_NAME = 'ai-learning-cache-v1';
const ASSETS_TO_CACHE = [
  '/',
  '/login',
  '/register',
  '/dashboard',
  '/offline',  // Add offline page
  '/static/manifest.json',
  '/static/js/register-sw.js',
  // CSS
  'https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css',
  'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css',
  // JavaScript
  'https://cdn.jsdelivr.net/npm/axios/dist/axios.min.js',
  // Add your icons here when they're created
  '/static/images/icon-192x192.png',
  '/static/images/icon-512x512.png',
  '/static/images/icon-152x152.png',
  '/static/images/icon-180x180.png',
  '/static/images/icon-167x167.png',
  '/static/images/favicon-32x32.png',
  '/static/images/favicon-16x16.png'
];

// Install event - cache assets
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('Opened cache');
        return cache.addAll(ASSETS_TO_CACHE);
      })
  );
});

// Activate event - clean old caches
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          if (cacheName !== CACHE_NAME) {
            console.log('Deleting old cache:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
  return self.clients.claim();
});

// Fetch event - serve from cache or network with network-first strategy for API routes
self.addEventListener('fetch', event => {
  // Skip cross-origin requests
  if (!event.request.url.startsWith(self.location.origin)) {
    return;
  }
  
  // For API or dynamic routes (POST requests or routes that might change data)
  if (
    event.request.method !== 'GET' ||
    event.request.url.includes('/generate') ||
    event.request.url.includes('/chat') ||
    event.request.url.includes('/submit')
  ) {
    // For API routes, try network only and fail gracefully
    event.respondWith(
      fetch(event.request)
        .catch(() => {
          // For navigation, go to offline page
          if (event.request.mode === 'navigate') {
            return caches.match('/offline');
          }
          
          // For API calls, return a standardized error
          return new Response(JSON.stringify({
            error: 'You are currently offline. Please check your connection and try again.'
          }), {
            status: 503,
            headers: { 'Content-Type': 'application/json' }
          });
        })
    );
    return;
  }
  
  // For page navigation - network first, fallback to cache, then offline page
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request)
        .catch(() => {
          return caches.match(event.request)
            .then(cachedResponse => {
              if (cachedResponse) {
                return cachedResponse;
              }
              // If the page is not in cache, show offline page
              return caches.match('/offline');
            });
        })
    );
    return;
  }
  
  // For static assets - cache first, then network
  event.respondWith(
    caches.match(event.request)
      .then(cachedResponse => {
        // Return cached response if found
        if (cachedResponse) {
          return cachedResponse;
        }
        
        // Otherwise, fetch from network
        return fetch(event.request)
          .then(response => {
            // Don't cache if response is not valid
            if (!response || response.status !== 200 || response.type !== 'basic') {
              return response;
            }
            
            // Clone the response to put in cache
            const responseToCache = response.clone();
            caches.open(CACHE_NAME)
              .then(cache => {
                cache.put(event.request, responseToCache);
              });
              
            return response;
          })
          .catch(error => {
            console.log('Fetch failed:', error);
            // For style or scripts, try to return a fallback
            if (
              event.request.destination === 'style' ||
              event.request.destination === 'script'
            ) {
              // Return empty CSS or JavaScript
              const contentType = event.request.destination === 'style' ? 'text/css' : 'application/javascript';
              return new Response('/* Offline fallback */', {
                status: 200,
                headers: { 'Content-Type': contentType }
              });
            }
            
            // For images, return a fallback placeholder
            if (event.request.destination === 'image') {
              return caches.match('/static/images/offline-placeholder.png')
                .catch(() => {
                  // If placeholder not available, return transparent 1x1 pixel PNG
                  return new Response(
                    new Uint8Array([
                      0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00, 0x00, 0x00, 0x0d, 
                      0x49, 0x48, 0x44, 0x52, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01, 
                      0x08, 0x06, 0x00, 0x00, 0x00, 0x1f, 0x15, 0xc4, 0x89, 0x00, 0x00, 0x00, 
                      0x0a, 0x49, 0x44, 0x41, 0x54, 0x78, 0x9c, 0x63, 0x00, 0x01, 0x00, 0x00, 
                      0x05, 0x00, 0x01, 0x0d, 0x0a, 0x2d, 0xb4, 0x00, 0x00, 0x00, 0x00, 0x49, 
                      0x45, 0x4e, 0x44, 0xae, 0x42, 0x60, 0x82
                    ]).buffer,
                    {
                      status: 200,
                      headers: { 'Content-Type': 'image/png' }
                    }
                  );
                });
            }
            
            throw error;
          });
      })
  );
}); 