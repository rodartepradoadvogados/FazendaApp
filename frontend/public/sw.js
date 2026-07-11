/* Service worker do app móvel (/app).
   Objetivo: o app ABRIR mesmo sem internet (casca + páginas do /app em cache).
   Os DADOS offline (agenda, listas, fila de lançamentos) são tratados pela
   aplicação em localStorage (lib/offline.ts) — aqui só cuidamos dos arquivos. */
const CACHE = "fazenda-app-v1";
const PAGINAS_APP = ["/app", "/app/lancar", "/app/rebanho", "/app/menu"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(PAGINAS_APP).catch(() => {}))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((chaves) =>
      Promise.all(chaves.filter((c) => c !== CACHE && c.startsWith("fazenda-app")).map((c) => caches.delete(c)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return; // API e externos: rede direta

  // Navegação nas telas do app: rede primeiro (conteúdo novo), cache se offline.
  if (req.mode === "navigate" && (url.pathname === "/app" || url.pathname.startsWith("/app/"))) {
    event.respondWith(
      fetch(req)
        .then((res) => {
          const copia = res.clone();
          caches.open(CACHE).then((cache) => cache.put(req, copia));
          return res;
        })
        .catch(() => caches.match(req).then((hit) => hit || caches.match("/app")))
    );
    return;
  }

  // Arquivos estáticos com hash (JS/CSS/fontes) e ícones: cache primeiro.
  if (url.pathname.startsWith("/_next/static/") || url.pathname.startsWith("/icons/")) {
    event.respondWith(
      caches.match(req).then(
        (hit) =>
          hit ||
          fetch(req).then((res) => {
            const copia = res.clone();
            caches.open(CACHE).then((cache) => cache.put(req, copia));
            return res;
          })
      )
    );
  }
});
