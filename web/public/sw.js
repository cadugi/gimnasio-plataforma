/* Top Fitness · avisos. Ámbito limitado a /reservas/. No guarda NADA en caché: ni datos personales, ni disponibilidad, ni reservas. */
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));

self.addEventListener('push', event => {
  let d = {};
  try { d = event.data ? event.data.json() : {}; } catch (_) {}
  const title = typeof d.title === 'string' ? d.title.slice(0, 80) : 'Top Fitness';
  const body = typeof d.body === 'string' ? d.body.slice(0, 200) : 'Tienes un aviso nuevo. Ábrelo para verlo.';
  event.waitUntil(self.registration.showNotification(title, {
    body, icon: '/reservas/icons/icon-192.png', badge: '/reservas/icons/favicon-64.png', lang: 'es',
    tag: typeof d.tag === 'string' ? d.tag : undefined, requireInteraction: d.requireInteraction === true,
    data: { url: typeof d.url === 'string' ? d.url : '/reservas/' }
  }));
});

/* Abrir el aviso NO acepta nada: solo lleva a la pantalla donde la persona decide. */
self.addEventListener('notificationclick', event => {
  event.notification.close();
  let url = new URL('/reservas/', self.location.origin);
  try {
    const u = new URL(event.notification.data && event.notification.data.url, self.location.origin);
    if (u.origin === self.location.origin && u.pathname.startsWith('/reservas/')) url = u;
  } catch (_) {}
  event.waitUntil((async () => {
    const list = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const c of list) {
      if (!c.url.startsWith(self.location.origin + '/reservas/')) continue;
      try { const w = await c.focus(); if (w && 'navigate' in w) { await w.navigate(url.href); return; } } catch (_) {}   // si no se puede reutilizar la pestaña, se abre una nueva
    }
    return self.clients.openWindow(url.href);
  })());
});

/* Sin conexión: solo se reemplaza una navegación fallida por un mensaje claro. Nunca se sirve nada guardado. */
const OFFLINE = '<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Sin conexión</title>' +
  '<body style="font:20px/1.5 system-ui,sans-serif;margin:0;padding:24px;background:#111;color:#fff"><h1 style="font-size:28px">Sin conexión</h1>' +
  '<p>No se puede confirmar ninguna reserva ni oferta ahora mismo.</p><p>Comprueba que tienes internet y vuelve a intentarlo.</p>' +
  '<p><a href="/reservas/" style="display:inline-block;min-height:48px;padding:12px 20px;background:#fff;color:#111;border-radius:8px;text-decoration:none;font-weight:700">Reintentar</a></p></body></html>';
self.addEventListener('fetch', event => {
  if (event.request.mode !== 'navigate') return;
  event.respondWith(fetch(event.request).catch(() => new Response(OFFLINE, { status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' } })));
});
