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
};

export default config;
