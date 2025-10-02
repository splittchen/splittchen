// Splittchen Service Worker for PWA functionality
const CACHE_NAME = 'splittchen-v1.0.0';
const STATIC_CACHE_NAME = 'splittchen-static-v1.0.0';

// Cache static resources for offline functionality
const STATIC_RESOURCES = [
    '/',
    '/static/favicon.ico',
    '/static/favicon-16x16.png',
    '/static/favicon-32x32.png',
    '/static/apple-touch-icon.png',
    '/static/android-chrome-192x192.png',
    '/static/android-chrome-512x512.png',
    '/static/site.webmanifest',
    // External resources (CDN)
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css',
    'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css',
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js',
    'https://cdn.socket.io/4.7.2/socket.io.min.js',
    'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap'
];

// Install event - cache static resources
self.addEventListener('install', event => {
    console.log('[SW] Installing service worker...');

    event.waitUntil(
        Promise.all([
            caches.open(STATIC_CACHE_NAME).then(cache => {
                console.log('[SW] Caching static resources');
                return cache.addAll(STATIC_RESOURCES.slice(0, 8)); // Cache local resources only initially
            }),
            // Skip waiting to activate immediately
            self.skipWaiting()
        ])
    );
});

// Activate event - cleanup old caches
self.addEventListener('activate', event => {
    console.log('[SW] Activating service worker...');

    event.waitUntil(
        Promise.all([
            // Clean up old caches
            caches.keys().then(cacheNames => {
                return Promise.all(
                    cacheNames.map(cacheName => {
                        if (cacheName !== CACHE_NAME && cacheName !== STATIC_CACHE_NAME) {
                            console.log('[SW] Deleting old cache:', cacheName);
                            return caches.delete(cacheName);
                        }
                    })
                );
            }),
            // Take control immediately
            self.clients.claim()
        ])
    );
});

// Fetch event - serve cached resources when offline
self.addEventListener('fetch', event => {
    const url = new URL(event.request.url);

    // Skip cross-origin requests and non-GET requests for caching
    if (event.request.method !== 'GET') {
        return;
    }

    // Handle static resources
    if (url.pathname.startsWith('/static/') || STATIC_RESOURCES.includes(event.request.url)) {
        event.respondWith(
            caches.match(event.request).then(response => {
                if (response) {
                    return response;
                }

                // Fetch and cache if not in cache
                return fetch(event.request).then(response => {
                    // Don't cache if response is not ok
                    if (!response || response.status !== 200 || response.type !== 'basic') {
                        return response;
                    }

                    const responseToCache = response.clone();
                    caches.open(STATIC_CACHE_NAME).then(cache => {
                        cache.put(event.request, responseToCache);
                    });

                    return response;
                });
            }).catch(() => {
                // Fallback for offline scenarios
                if (url.pathname === '/') {
                    return new Response('<h1>Splittchen</h1><p>Please check your internet connection.</p>', {
                        headers: { 'Content-Type': 'text/html' }
                    });
                }
            })
        );
        return;
    }

    // For HTML pages, use network-first strategy with fallback
    if (event.request.destination === 'document' || event.request.headers.get('Accept')?.includes('text/html')) {
        event.respondWith(
            fetch(event.request).catch(() => {
                return caches.match('/').then(response => {
                    return response || new Response(
                        '<h1>Splittchen - Offline</h1><p>Please check your internet connection to access groups.</p>',
                        { headers: { 'Content-Type': 'text/html' } }
                    );
                });
            })
        );
        return;
    }

    // For external CDN resources, cache them
    if (url.hostname !== self.location.hostname && STATIC_RESOURCES.includes(event.request.url)) {
        event.respondWith(
            caches.match(event.request).then(response => {
                return response || fetch(event.request).then(response => {
                    if (response.status === 200) {
                        const responseToCache = response.clone();
                        caches.open(STATIC_CACHE_NAME).then(cache => {
                            cache.put(event.request, responseToCache);
                        });
                    }
                    return response;
                });
            })
        );
        return;
    }
});

// Background sync for offline actions (future enhancement)
self.addEventListener('sync', event => {
    if (event.tag === 'expense-sync') {
        event.waitUntil(syncExpenses());
    }
});

// Placeholder for future background sync functionality
async function syncExpenses() {
    console.log('[SW] Background sync for expenses (placeholder)');
    // Future implementation: sync offline actions when back online
}

// Push notification handler (future enhancement)
self.addEventListener('push', event => {
    if (event.data) {
        const data = event.data.json();

        const options = {
            body: data.body,
            icon: '/static/android-chrome-192x192.png',
            badge: '/static/favicon-32x32.png',
            tag: 'splittchen-notification',
            requireInteraction: false
        };

        event.waitUntil(
            self.registration.showNotification(data.title || 'Splittchen', options)
        );
    }
});

// Handle notification clicks
self.addEventListener('notificationclick', event => {
    event.notification.close();

    event.waitUntil(
        clients.matchAll({ type: 'window' }).then(clientList => {
            // If a window is already open, focus it
            for (const client of clientList) {
                if (client.url === self.registration.scope && 'focus' in client) {
                    return client.focus();
                }
            }

            // Otherwise, open a new window
            if (clients.openWindow) {
                return clients.openWindow('/');
            }
        })
    );
});

console.log('[SW] Service worker script loaded');