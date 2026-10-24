import type { CapacitorConfig } from "@capacitor/cli";

// ENDEREÇO: o site agora tem domínio próprio (milk.cowdata.com.br; a API fica
// em api.milk.cowdata.com.br). A URL de server.url fica soldada dentro do
// .apk gerado — trocar de novo exige novo .apk em todos os celulares E apaga
// o storage da origem antiga: localStorage (token, cache) E IndexedDB (fila
// de lançamentos e FOTOS pendentes, ver lib/outboxDb.ts). A troca do endereço
// do Vercel para o domínio próprio já fez o celular esquecer o login e a fila
// local (avisado aos usuários, ver docs/APP_INSTALACAO.md). O endereço antigo
// (fazenda-app-jfye.vercel.app) continua válido e segue em allowNavigation
// por segurança. Não mude appId, nem a chave debug.keystore: o app novo
// precisa atualizar POR CIMA do instalado.
const config: CapacitorConfig = {
  appId: "br.com.cowdata.fazenda",
  appName: "CowData Milk",

  // Copiada para android/app/src/main/assets/public/ pelo `cap sync`. NÃO é
  // o app — o app vem de server.url, abaixo. Aqui mora só a casca offline
  // (offline.html) que aparece quando a WebView não consegue carregar o
  // site (1ª abertura sem internet, DNS fora, deploy fora do ar).
  webDir: "capacitor-www",

  server: {
    url: "https://milk.cowdata.com.br/app",

    // Hosts que a WebView pode navegar internamente — qualquer outro vira
    // link externo (abre o Chrome). O endereço antigo do Vercel é mantido
    // por segurança.
    allowNavigation: ["milk.cowdata.com.br", "fazenda-app-jfye.vercel.app"],

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
