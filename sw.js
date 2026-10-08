// Online usa la rete; senza connessione mostra l'ultima copia salvata.
const PREFIX = `sport-os:${new URL(self.registration.scope).pathname}:`;
const CACHE = PREFIX + 'v1';
const assetUrl = path => new URL(path, self.registration.scope).href;
const HOME = assetUrl('index.html');
const DATA = assetUrl('dati.js');
const FILES = ['index.html', 'calendario_sportivo.html', 'dati.js', 'manifest.json', 'icon-192.png', 'icon-512.png'].map(assetUrl);

self.addEventListener('install', event => {
    event.waitUntil((async () => {
        const cache = await caches.open(CACHE);
        await cache.addAll(FILES.map(url => new Request(url, { cache: 'reload' })));
        await self.skipWaiting();
    })());
});

self.addEventListener('activate', event => {
    event.waitUntil((async () => {
        for (const key of await caches.keys()) if (key.startsWith(PREFIX) && key !== CACHE) await caches.delete(key);
        await self.clients.claim();
    })());
});

self.addEventListener('fetch', event => {
    if (event.request.method !== 'GET') return;
    const canonical = new URL(event.request.url);
    canonical.search = '';
    const key = canonical.href === self.registration.scope ? HOME : canonical.href;
    if (!FILES.includes(key)) return;
    event.respondWith((async () => {
        const cache = await caches.open(CACHE);
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 6000);
        try {
            const response = await fetch(event.request, { cache: 'no-store', signal: controller.signal });
            if (!response.ok) throw new Error('Download fallito');
            if (key === DATA) {
                const text = await response.clone().text();
                if (!text.startsWith('window.calendarData = ') || !text.includes('window.calendarMeta = ')) throw new Error('Dati non validi');
            }
            await cache.put(key, response.clone());
            return response;
        } catch (error) {
            const saved = await cache.match(key);
            if (saved) return saved;
            throw error;
        } finally { clearTimeout(timeout); }
    })());
});
