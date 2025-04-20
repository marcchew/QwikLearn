// Service Worker for QwikLearn
const CACHE_NAME = 'ai-learning-cache-v2';  // Increment version to force cache refresh
const STATIC_CACHE = 'ai-learning-static-v2';
const API_CACHE = 'ai-learning-api-v2';
const IMG_CACHE = 'ai-learning-img-v2';

// Core assets that must be cached for the app to work
const CORE_ASSETS = [
  '/',
  '/offline',
  '/static/manifest.json',
  '/static/js/register-sw.js',
  '/static/images/icon-192x192.png',
  // Include minimal CSS needed for offline mode
  'https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css'
];

// Additional assets that should be cached but aren't critical
const SECONDARY_ASSETS = [
  '/login',
  '/register',
  '/dashboard',
  // CSS
  'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css',
  // JavaScript
  'https://cdn.jsdelivr.net/npm/axios/dist/axios.min.js',
  // Icons
  '/static/images/icon-512x512.png',
  '/static/images/icon-152x152.png',
  '/static/images/icon-180x180.png',
  '/static/images/icon-167x167.png',
  '/static/images/favicon-32x32.png',
  '/static/images/favicon-16x16.png'
];

// Install event - cache core assets immediately
self.addEventListener('install', event => {
  console.log('Service Worker: Installing...');
  
  // Cache core assets immediately
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then(cache => {
        console.log('Service Worker: Caching core assets');
        // Use Promise.all to cache everything in parallel
        return Promise.all(
          CORE_ASSETS.map(url => {
            // Fetch with cache-busting parameter to ensure fresh content
            return fetch(`${url}${url.includes('?') ? '&' : '?'}_sw-cache=${Date.now()}`, { 
              credentials: 'same-origin',
              headers: { 'Cache-Control': 'no-cache' }
            })
            .then(response => {
              if (!response.ok) {
                throw new Error(`Failed to fetch ${url}`);
              }
              return cache.put(url, response);
            })
            .catch(error => {
              console.error(`Failed to cache ${url}: ${error}`);
            });
          })
        );
      })
  );
  
  // Don't wait for activation, take control immediately
  self.skipWaiting();
});

// Activate event - clean old caches and take control
self.addEventListener('activate', event => {
  console.log('Service Worker: Activating...');
  
  // Clean up old caches
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          if (
            cacheName !== STATIC_CACHE && 
            cacheName !== API_CACHE && 
            cacheName !== IMG_CACHE
          ) {
            console.log('Service Worker: Deleting old cache:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    })
    .then(() => {
      console.log('Service Worker: Active and controlling');
      
      // Cache secondary assets in the background
      caches.open(STATIC_CACHE)
        .then(cache => {
          console.log('Service Worker: Caching secondary assets');
          SECONDARY_ASSETS.forEach(url => {
            fetch(url, { credentials: 'same-origin' })
              .then(response => {
                if (response.ok) {
                  cache.put(url, response);
                }
              })
              .catch(error => {
                console.log(`Failed to cache ${url}: ${error}`);
              });
          });
        });
    })
  );
  
  // Take control of clients immediately
  return self.clients.claim();
});

// Helper function to determine correct cache strategy
function strategy(url, request) {
  const domain = self.location.origin;
  
  // Use network first for API calls and dynamic content
  if (
    url.pathname.includes('/api/') ||
    url.pathname.includes('/generate') ||
    url.pathname.includes('/chat') ||
    url.pathname.includes('/submit') ||
    request.method !== 'GET'
  ) {
    return 'network-first';
  }
  
  // For images, use cache first
  if (
    request.destination === 'image' ||
    url.pathname.startsWith('/static/images/')
  ) {
    return 'cache-first';
  }
  
  // For core app pages, use network first but with cache fallback
  if (
    url.pathname === '/' ||
    url.pathname.startsWith('/dashboard') ||
    url.pathname.startsWith('/syllabi') ||
    url.pathname.startsWith('/assignments') ||
    url.pathname.startsWith('/todos') ||
    url.pathname.startsWith('/study-plans')
  ) {
    return 'network-first';
  }
  
  // Default to stale-while-revalidate for everything else
  return 'stale-while-revalidate';
}

// Function to determine which cache to use
function getCacheName(request) {
  if (request.destination === 'image') {
    return IMG_CACHE;
  }
  
  const url = new URL(request.url);
  if (
    url.pathname.includes('/api/') ||
    url.pathname.includes('/generate') ||
    url.pathname.includes('/chat')
  ) {
    return API_CACHE;
  }
  
  return STATIC_CACHE;
}

// Implement cache-first strategy
async function cacheFirst(request) {
  const cacheName = getCacheName(request);
  const cachedResponse = await caches.match(request);
  
  if (cachedResponse) {
    return cachedResponse;
  }
  
  try {
    const networkResponse = await fetch(request);
    
    // Only cache valid responses from our domain
    if (networkResponse.ok && request.url.startsWith(self.location.origin)) {
      const cache = await caches.open(cacheName);
      cache.put(request, networkResponse.clone());
    }
    
    return networkResponse;
  } catch (error) {
    // For images, return a fallback
    if (request.destination === 'image') {
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
    
    // For other resources, just propagate the error
    throw error;
  }
}

// Implement network-first strategy
async function networkFirst(request) {
  try {
    // Try from network first
    const networkResponse = await fetch(request);
    
    // If successful, cache it and return
    if (networkResponse.ok) {
      const cacheName = getCacheName(request);
      const cache = await caches.open(cacheName);
      cache.put(request, networkResponse.clone());
      return networkResponse;
    }
    
    // If not successful but status code isn't 4xx/5xx, try from cache
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }
    
    // Return the network response even if it's an error
    return networkResponse;
  } catch (error) {
    // Network error, try from cache
    const cachedResponse = await caches.match(request);
    
    if (cachedResponse) {
      return cachedResponse;
    }
    
    // If the request is for a page, return the offline page
    if (request.mode === 'navigate') {
      return caches.match('/offline');
    }
    
    // For API requests, return a JSON error
    if (request.destination === 'empty' && request.headers.get('accept').includes('application/json')) {
      return new Response(
        JSON.stringify({ error: 'You are currently offline. Please check your connection and try again.' }),
        {
          status: 503,
          headers: { 'Content-Type': 'application/json' }
        }
      );
    }
    
    // For style or scripts, return empty content
    if (request.destination === 'style' || request.destination === 'script') {
      const contentType = request.destination === 'style' ? 'text/css' : 'application/javascript';
      return new Response('/* Offline fallback */', {
        status: 200,
        headers: { 'Content-Type': contentType }
      });
    }
    
    // For other resources, propagate the error
    throw error;
  }
}

// Implement stale-while-revalidate strategy
async function staleWhileRevalidate(request) {
  const cacheName = getCacheName(request);
  
  // Try from cache first
  const cachedResponse = await caches.match(request);
  
  // Fetch from network in the background to update cache
  const fetchPromise = fetch(request)
    .then(networkResponse => {
      if (networkResponse.ok) {
        // Update the cache
        caches.open(cacheName)
          .then(cache => cache.put(request, networkResponse.clone()));
      }
      return networkResponse;
    })
    .catch(error => {
      console.log(`Failed to fetch ${request.url}: ${error}`);
      throw error;
    });
  
  // Return cached response immediately if available
  if (cachedResponse) {
    return cachedResponse;
  }
  
  // Otherwise wait for network response
  return fetchPromise;
}

// Fetch event - intelligent caching strategies
self.addEventListener('fetch', event => {
  const request = event.request;
  
  // Skip cross-origin requests
  if (!request.url.startsWith(self.location.origin) && !request.url.startsWith('https://cdn.jsdelivr.net')) {
    return;
  }
  
  const url = new URL(request.url);
  const fetchStrategy = strategy(url, request);
  
  if (fetchStrategy === 'cache-first') {
    event.respondWith(cacheFirst(request));
  } else if (fetchStrategy === 'network-first') {
    event.respondWith(networkFirst(request));
  } else if (fetchStrategy === 'stale-while-revalidate') {
    event.respondWith(staleWhileRevalidate(request));
  }
}); 