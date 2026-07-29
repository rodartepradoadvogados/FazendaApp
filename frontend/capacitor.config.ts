import type { CapacitorConfig } from "@capacitor/cli";

// PROVISÓRIO: URL do site apontada aqui fica soldada dentro do .apk gerado —
// trocar depois exige novo .apk em todos os celulares E apaga o localStorage
// da origem antiga (token, cache, fila de lançamentos pendentes). Antes de
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
    SplashScreen: {
      // O site pode demorar em 3G rural — hide() é chamado manualmente pelo
      // app assim que a tela carrega (ver lib/nativo.ts), mas mantém um teto
      // de segurança aqui: se por algum motivo o hide() manual nunca rodar
      // (erro de JS antes do efeito, por exemplo), o splash não fica preso
      // pra sempre.
      launchShowDuration: 4000,
      launchAutoHide: true,
      // Vinho claro (misto) — mesma cor de COR_TOPO.vinho.clara em
      // lib/themeColorTopo.ts (fonte única, também usada pelo manifest PWA e
      // pela <meta name="theme-color">). Sem variação por paleta aqui porque
      // a paleta é lida do localStorage, que o splash nativo não acessa.
      backgroundColor: "#3A0F1A",
      androidScaleType: "CENTER_CROP",
      showSpinner: false,
    },
    StatusBar: {
      style: "DARK", // ícones claros sobre o header escuro do app
      backgroundColor: "#3A0F1A",
      overlaysWebView: false, // o layout já reserva a faixa de segurança do topo
    },
  },
};

export default config;
