/* Service worker do app móvel (/app).
   Objetivo: o app ABRIR mesmo sem internet (casca + páginas do /app em cache).
   Os DADOS offline (agenda, listas, fila de lançamentos e fotos) são
   tratados pela aplicação em IndexedDB (lib/offline.ts, lib/outboxDb.ts) —
   aqui só cuidamos dos arquivos estáticos (casca do app). */
const CACHE = "fazenda-app-v2";
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

// Web Push: notificação nativa mesmo com o app fechado, para os MESMOS
// alertas do sininho (contas vencendo, estoque baixo, pendências de agenda
// etc. — ver backend/fazenda/api/routers/push.py, que decide o quê/quando).
self.addEventListener("push", (event) => {
  let dados = { title: "Fazenda Estreito Ponte de Pedra", body: "Você tem uma nova pendência.", url: "/agenda" };
  try {
    if (event.data) dados = { ...dados, ...event.data.json() };
  } catch (e) { /* payload não veio em JSON — usa os padrões acima */ }
  event.waitUntil(
    Promise.all([
      self.registration.showNotification(dados.title, {
        body: dados.body,
        icon: "/icons/icone-192.png",
        badge: "/icons/icone-192.png",
        data: { url: dados.url || "/agenda" },
      }),
      // Bolinha com a quantidade de eventos no ícone do app instalado
      // (Badging API) — só o push da Agenda do dia informa `count`; os
      // demais (pendências/comunicados) não mexem no badge.
      typeof dados.count === "number" && "setAppBadge" in self.registration
        ? (dados.count > 0 ? self.registration.setAppBadge(dados.count) : self.registration.clearAppBadge()).catch(() => {})
        : Promise.resolve(),
    ])
  );
});

// Clique na notificação: foca uma aba já aberta no destino (ou abre uma nova).
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || "/agenda";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if (client.url.includes(url) && "focus" in client) return client.focus();
      }
      if (self.clients.openWindow) return self.clients.openWindow(url);
    })
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

  // Arquivos estáticos com hash (JS/CSS/fontes) e ícones: cache primeiro —
  // MAS só quando pedidos por uma página do /app. O `register("/sw.js")`
  // (sem `scope`) abrange o site INTEIRO por padrão (raiz "/"), não só
  // "/app" — sem este filtro, visitar o /app uma vez bastava pra prender
  // TODAS as páginas do site (Central de Protocolos, Sanidade…) num bundle
  // JS congelado no que estava em cache na 1ª visita, nunca mais atualizado
  // por um novo deploy (bug real, caso relatado: "nada mudou" mesmo após
  // vários merges). `req.referrer` é a página que disparou o pedido do
  // arquivo — vazio numa navegação direta, então checamos por padrão.
  if ((url.pathname.startsWith("/_next/static/") || url.pathname.startsWith("/icons/")) && req.referrer && new URL(req.referrer).pathname.startsWith("/app")) {
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
