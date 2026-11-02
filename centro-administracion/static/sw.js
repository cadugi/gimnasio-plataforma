// Service worker mínimo: hace la web instalable. No guarda nada en caché (los datos de caja son privados y deben ser siempre actuales).
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", (e) => {
  if (e.request.method !== "GET") return;
  e.respondWith(fetch(e.request).catch(() => new Response("Sin conexión. Vuelve a intentarlo cuando tengas internet.", { status: 503, headers: { "Content-Type": "text/plain; charset=utf-8" } })));
});
