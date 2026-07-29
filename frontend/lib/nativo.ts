"use client";
// Ponte com o Capacitor (app Android nativo) — só existe quando o site roda
// dentro do WebView do app, nunca no navegador comum/PWA. Todo acesso nativo
// passa por aqui, com import DINÂMICO dentro de função (nunca no topo do
// módulo): os proxies de plugin do Capacitor resolvem contra `window`, e um
// import no topo pode quebrar a renderização no servidor (Next SSR) — mesmo
// padrão já usado no repo para telas pesadas (ver LancarTela.tsx).
let capacitorCore: typeof import("@capacitor/core") | null = null;

async function core() {
  if (typeof window === "undefined") return null;
  if (!capacitorCore) capacitorCore = await import("@capacitor/core");
  return capacitorCore;
}

/** true só dentro do app Android (Capacitor); false no navegador/PWA/SSR. */
export async function ehApp(): Promise<boolean> {
  const c = await core();
  return c?.Capacitor?.isNativePlatform() ?? false;
}

/** Esconde a splash nativa assim que a tela carregou de verdade — a config
 *  (capacitor.config.ts) já tem um teto de segurança (launchAutoHide) caso
 *  isto nunca rode. Não faz nada fora do app nativo. */
export async function esconderSplash() {
  if (!(await ehApp())) return;
  const { SplashScreen } = await import("@capacitor/splash-screen");
  await SplashScreen.hide().catch(() => {});
}

/** Ajusta a barra de status (ícones claros/escuros) ao tema atual. Não faz
 *  nada fora do app nativo. */
export async function ajustarStatusBar(escuro: boolean) {
  if (!(await ehApp())) return;
  const { StatusBar, Style } = await import("@capacitor/status-bar");
  await StatusBar.setStyle({ style: escuro ? Style.Dark : Style.Dark }).catch(() => {});
  // Sempre Style.Dark (ícones claros) — o header do app é sempre escuro
  // (vinho/verde/azul), em ambos os temas claro/escuro do app.
}

/** Registra o botão voltar físico do Android: navega como o navegador
 *  (history.back()) e só deixa fechar o app na raiz do /app. Retorna a
 *  função de limpeza (ou no-op fora do app nativo). */
export async function registrarBotaoVoltar(estaNaRaiz: () => boolean): Promise<() => void> {
  if (!(await ehApp())) return () => {};
  const { App } = await import("@capacitor/app");
  const handle = await App.addListener("backButton", () => {
    if (estaNaRaiz()) {
      App.exitApp();
    } else {
      history.back();
    }
  });
  return () => { handle.remove(); };
}

// A URL que o backend manda no push (ver url_destino() em
// backend/fazenda/api/routers/push.py) é uma rota do SITE (/agenda,
// /financeiro, /estoque, /portal, /aprovacoes) — o app nativo abre a casca
// /app; só a Agenda tem equivalente dentro dela. Demais rotas abrem mesmo
// assim (o site inteiro carrega dentro da WebView, só sem a casca do /app).
function rotaDoApp(url: string): string {
  return url === "/agenda" ? "/app" : url;
}

/** Registra o aparelho para receber notificações do app nativo (FCM) — canal
 *  irmão do Web Push do navegador/PWA (ver components/NotificationBell.tsx),
 *  que não é confiável dentro da WebView do Capacitor com o app fechado.
 *  Fora do app nativo (navegador/PWA/SSR) não faz nada.
 *
 *  Fluxo: checa/pede a permissão de notificação (Android 13+ exige o pedido
 *  em runtime) → PushNotifications.register() → o evento "registration"
 *  devolve o token → manda pro backend (POST /push/registrar-fcm). Chamar em
 *  toda abertura do app é o esperado — o token pode rotacionar sozinho, e o
 *  registro no backend é idempotente (upsert por token).
 *
 *  Best-effort: qualquer falha (usuário negou a permissão, aparelho sem
 *  Google Play Services, erro de rede ao mandar o token) só gera
 *  console.warn — push é canal ADICIONAL, nunca pode impedir o app de abrir
 *  nem travar a tela.
 *
 *  `aoTocarNotificacao` recebe a rota (já traduzida pra dentro do /app,
 *  ver rotaDoApp) quando o usuário toca numa notificação com o app aberto
 *  em segundo plano — quem chama decide como navegar (ex.: router.push). */
export async function registrarPushNativo(aoTocarNotificacao?: (rota: string) => void): Promise<() => void> {
  if (!(await ehApp())) return () => {};
  try {
    const { PushNotifications } = await import("@capacitor/push-notifications");

    let permissao = await PushNotifications.checkPermissions();
    if (permissao.receive === "prompt" || permissao.receive === "prompt-with-rationale") {
      permissao = await PushNotifications.requestPermissions();
    }
    if (permissao.receive !== "granted") return () => {}; // usuário negou — sai quieto, sem re-perguntar

    const hRegistro = await PushNotifications.addListener("registration", async (token) => {
      try {
        const [{ registrarTokenFcm }, { Device }] = await Promise.all([
          import("@/lib/api"),
          import("@capacitor/device"),
        ]);
        const [info, id] = await Promise.all([Device.getInfo(), Device.getId()]);
        await registrarTokenFcm({
          token: token.value, plataforma: "android",
          modelo: `${info.manufacturer || ""} ${info.model || ""}`.trim() || undefined,
          device_id: id.identifier,
        });
      } catch (e) {
        console.warn("Falha ao registrar token de push nativo:", e);
      }
    });
    const hErro = await PushNotifications.addListener("registrationError", (e) => {
      console.warn("Falha ao registrar para push nativo:", e.error);
    });
    const hToque = await PushNotifications.addListener("pushNotificationActionPerformed", (acao) => {
      const url = (acao.notification?.data?.url as string) || "/app";
      aoTocarNotificacao?.(rotaDoApp(url));
    });

    await PushNotifications.register();
    return () => { hRegistro.remove(); hErro.remove(); hToque.remove(); };
  } catch (e) {
    console.warn("Push nativo indisponível neste aparelho:", e);
    return () => {};
  }
}

/** Remove o token FCM deste aparelho do backend — chamado no logout do app
 *  nativo, senão o próximo funcionário a usar o mesmo celular continuaria
 *  recebendo as notificações do usuário anterior. Best-effort: não bloqueia
 *  o logout se a rede falhar. Não faz nada fora do app nativo. */
export async function removerPushNativo(): Promise<void> {
  if (!(await ehApp())) return;
  try {
    const [{ PushNotifications }, { removerTokenFcm }] = await Promise.all([
      import("@capacitor/push-notifications"),
      import("@/lib/api"),
    ]);
    await PushNotifications.unregister().catch(() => {});
    await removerTokenFcm();
  } catch { /* best-effort — logout não pode travar por causa disso */ }
}
