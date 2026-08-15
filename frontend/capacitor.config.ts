import type { CapacitorConfig } from "@capacitor/cli";

// PROVISÓRIO: URL do site apontada aqui fica soldada dentro do .apk gerado —
// trocar depois exige novo .apk em todos os celulares E apaga o storage
// da origem antiga: localStorage (token, cache) E IndexedDB (fila de
// lançamentos e FOTOS pendentes, ver lib/outboxDb.ts) — só trocar de
// domínio com todos os celulares sincronizados (fila vazia). Antes de
// gerar o primeiro .apk para os funcionários, confirmar com o usuário se
// "fazenda-app-jfye.vercel.app" é definitivo ou se vai existir um domínio
// próprio — ver docs/APP_INSTALACAO.md e README do app Capacitor.
const config: CapacitorConfig = {
  appId: "br.com.cowdata.fazenda",
  appName: "CowData Fazenda",

  // Copiada para android/app/src/main/assets/public/ pelo `cap sync`. NÃO é
  // o app — o app vem de server.url, abaixo. Aqui mora só a casca offline
  // (offline.html) que aparece quando a WebView não consegue carregar o
  // site (1ª abertura sem internet, DNS fora, deploy fora do ar).
  webDir: "capacitor-www",

  server: {
    url: "https://fazenda-app-jfye.vercel.app/app",

    // Hosts que a WebView pode navegar internamente — qualquer outro vira
    // link externo (abre o Chrome). Ajustar se/quando o domínio mudar.
    allowNavigation: ["fazenda-app-jfye.vercel.app"],

    // Página local mostrada quando o carregamento de server.url falha.
    errorPath: "offline.html",

    cleartext: false,
  },

  android: {
    allowMixedContent: false,
    webContentsDebuggingEnabled: true, // chrome://inspect — desligar no release final
  },

  plugins: {
    // Faz fetch()/XMLHttpRequest do app inteiro passar pela ponte nativa
    // (OkHttp no Android) em vez do motor de rede embutido na WebView —
    // diagnóstico real (ago/2026): o mesmo celular, mesma rede 4G, sincroniza
    // sem problema pelo PWA (roda em cima do Chrome instalado, que se
    // autoatualiza) mas nunca consegue enviar nada pelo app Capacitor
    // instalado (roda na Android System WebView, componente separado do
    // Chrome, que em aparelho sem atualização frequente — comum em uso
    // rural — pode ficar com TLS/certificado desatualizado o bastante para
    // toda requisição falhar com "TypeError: Failed to fetch", mesmo com
    // sinal de rádio bom). A ponte nativa usa a pilha de rede do próprio
    // Android (atualizada via Google Play Services, independente da
    // WebView), contornando esse problema. Continua funcionando com
    // FormData/Blob (upload de fotos, ver lib/offline.ts) — o fetch/XHR
    // corrigido aqui suporta os dois, diferente da API CapacitorHttp.post()
    // chamada direto (essa sim exigiria converter para base64).
    CapacitorHttp: {
      enabled: true,
    },
    SplashScreen: {
      // O site pode demorar em 3G rural — hide() é chamado manualmente pelo
      // app assim que a tela carrega (ver lib/nativo.ts), mas mantém um teto
      // de segurança aqui: se por algum motivo o hide() manual nunca rodar
      // (erro de JS antes do efeito, por exemplo), o splash não fica preso
      // pra sempre.
      launchShowDuration: 4000,
      launchAutoHide: true,
      // Marinho institucional — mesma cor de COR_TOPO.azul.clara em
      // lib/themeColorTopo.ts (fonte única, também usada pelo manifest PWA e
      // pela <meta name="theme-color">). Sem variação por paleta aqui porque
      // a paleta é lida do localStorage, que o splash nativo não acessa.
      backgroundColor: "#0A1F36",
      androidScaleType: "CENTER_CROP",
      showSpinner: false,
    },
    StatusBar: {
      style: "DARK", // ícones claros sobre o header escuro do app
      backgroundColor: "#0A1F36",
      overlaysWebView: false, // o layout já reserva a faixa de segurança do topo
    },
  },
};

export default config;
