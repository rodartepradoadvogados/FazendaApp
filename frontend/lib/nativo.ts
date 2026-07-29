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
