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

/** true dentro do app nativo (Capacitor) OU do PWA instalado em modo
 *  standalone (mesma detecção de components/mobile/InstalarApp.tsx) — os
 *  dois casos em que a UI deve usar a casca mobile (/app) em qualquer
 *  navegação "para a raiz" (login, sessão expirada, sem permissão etc.),
 *  nunca o site desktop completo (/). Diferente de ehApp(): não decide
 *  acesso a plugin nativo nenhum, só qual casca mostrar — por isso cobre
 *  também o PWA, que ehApp() sozinho não vê (Capacitor.isNativePlatform()
 *  é false fora do app Android). */
export async function ehAppOuPwa(): Promise<boolean> {
  if (typeof window === "undefined") return false;
  const standalone = window.matchMedia("(display-mode: standalone)").matches
    || (window.navigator as unknown as { standalone?: boolean }).standalone === true;
  return standalone || ehApp();
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
  // Sempre Style.Dark (ícones claros) — o header do app é sempre marinho,
  // em ambos os temas claro/escuro do app.
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

function baixarViaAncora(blob: Blob, nomeArquivo: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nomeArquivo;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function blobParaBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve((reader.result as string).split(",")[1] ?? "");
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

/** Entrega ao usuário um arquivo gerado no cliente (Blob) e já abre a folha
 *  de COMPARTILHAR — usado pelo botão "Compartilhar" (envia por WhatsApp,
 *  e-mail etc.), distinto do botão "Baixar" (ver salvarArquivo abaixo, que
 *  só salva, sem abrir nada). No navegador/PWA usa o mecanismo padrão (<a
 *  download> + blob: URL, clicado programaticamente) — sem noção de
 *  "compartilhar" ali, é idêntico a salvarArquivo. Dentro do app nativo
 *  (Capacitor Android) esse mesmo clique de <a> não dispara nada: a WebView
 *  do Bridge padrão do Capacitor (ver android/.../MainActivity.java — só
 *  `BridgeActivity`, sem `setDownloadListener`/`WebChromeClient` customizado)
 *  não tem um handler de download registrado, então o "clique" no <a> não
 *  produz erro nenhum nem download nenhum — some em silêncio. Por isso, só
 *  dentro do app, gravamos o arquivo no cache do app (@capacitor/filesystem)
 *  e abrimos a folha de compartilhar nativa (@capacitor/share), de onde o
 *  usuário salva/abre/envia o arquivo — caminho confiável dentro da WebView. */
export async function baixarArquivo(blob: Blob, nomeArquivo: string): Promise<void> {
  if (await ehApp()) {
    const [{ Filesystem, Directory }, { Share }] = await Promise.all([
      import("@capacitor/filesystem"),
      import("@capacitor/share"),
    ]);
    const base64 = await blobParaBase64(blob);
    const gravado = await Filesystem.writeFile({ path: nomeArquivo, data: base64, directory: Directory.Cache });
    await Share.share({ url: gravado.uri, title: nomeArquivo });
    return;
  }
  baixarViaAncora(blob, nomeArquivo);
}

/** Entrega ao usuário um arquivo gerado no cliente SEM abrir a folha de
 *  compartilhar — usado pelo botão "Baixar" (ver baixarArquivo acima para o
 *  "Compartilhar", que abre a folha nativa). Existe porque antes desta
 *  função só havia um caminho de entrega dentro do app, e ele SEMPRE
 *  compartilhava — clicar em "Exportar" jogava direto na folha de
 *  compartilhar do Android, sem opção de só baixar (pedido explícito do
 *  usuário para separar os dois). No navegador/PWA é idêntico a
 *  baixarArquivo (mesmo <a download>; não existe "compartilhar" por lá).
 *  Dentro do app nativo, grava em Directory.Documents (pasta persistente do
 *  app, não o cache usado por baixarArquivo/Share) e devolve o caminho
 *  gravado, para quem chamou avisar o usuário onde o arquivo ficou. */
export async function salvarArquivo(blob: Blob, nomeArquivo: string): Promise<{ uri: string } | undefined> {
  if (await ehApp()) {
    const { Filesystem, Directory } = await import("@capacitor/filesystem");
    const base64 = await blobParaBase64(blob);
    const gravado = await Filesystem.writeFile({ path: nomeArquivo, data: base64, directory: Directory.Documents });
    return { uri: gravado.uri };
  }
  baixarViaAncora(blob, nomeArquivo);
  return undefined;
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

// ── Cópia de segurança da sessão (@capacitor/preferences) ──
// "Manter conectado neste aparelho" promete não pedir login de novo (ver
// comentário em backend/fazenda/auth.py::TOKEN_VALIDADE_LONGA_S) — mas o
// token só vivia no localStorage da WebView, que o Android pode limpar sem
// avisar (atualização do componente WebView do sistema, "liberar espaço"
// etc.), sem que o app seja desinstalado nem o usuário peça. @capacitor/
// preferences grava em SharedPreferences nativo, bem mais durável. O
// localStorage continua sendo a fonte de verdade (é nele que getToken() e
// todo o resto do app lêem, de forma síncrona); isto é só uma cópia restaurada
// na abertura do app quando o localStorage aparece vazio (ver AuthShell).
const CHAVE_SESSAO_TOKEN = "token";
const CHAVE_SESSAO_USUARIO = "usuario";
const CHAVE_SESSAO_FAZENDA = "fazenda_atual";
// "conta_ativa" (ver lib/api.ts::getContaAtivaId) — 0 = Painel CowData,
// id>0 = a fazenda. Sem espelhar isto também, um dono/membro da Equipe
// CowData que force-fecha o app enquanto está NO Painel CowData e reabre
// depois (restaurarSessaoNativa) perderia essa marcação: a tela de troca de
// conta não saberia mais dizer qual conta é "aqui" logo após restaurar.
const CHAVE_SESSAO_CONTA_ATIVA = "conta_ativa";

/** Grava a sessão atual na cópia nativa — chamado só quando "Manter conectado"
 *  está marcado (ver lib/api.ts::login/selecionarFazenda/entrarPainelCowData).
 *  Best-effort, nunca trava o login por causa disso. Não faz nada fora do
 *  app nativo. */
export async function salvarSessaoNativa(token: string, usuario: unknown, fazendaAtual: unknown | null, contaAtiva: string | null = null): Promise<void> {
  if (!(await ehApp())) return;
  try {
    const { Preferences } = await import("@capacitor/preferences");
    await Preferences.set({ key: CHAVE_SESSAO_TOKEN, value: token });
    await Preferences.set({ key: CHAVE_SESSAO_USUARIO, value: JSON.stringify(usuario ?? null) });
    if (fazendaAtual) await Preferences.set({ key: CHAVE_SESSAO_FAZENDA, value: JSON.stringify(fazendaAtual) });
    else await Preferences.remove({ key: CHAVE_SESSAO_FAZENDA });
    if (contaAtiva != null) await Preferences.set({ key: CHAVE_SESSAO_CONTA_ATIVA, value: contaAtiva });
    else await Preferences.remove({ key: CHAVE_SESSAO_CONTA_ATIVA });
  } catch { /* best-effort */ }
}

/** Restaura a cópia nativa da sessão para dentro do localStorage — chamado
 *  uma vez na abertura do app (ver AuthShell), só quando o localStorage está
 *  vazio. Não faz nada fora do app nativo. */
export async function restaurarSessaoNativa(): Promise<void> {
  if (!(await ehApp())) return;
  try {
    const { Preferences } = await import("@capacitor/preferences");
    const { value: token } = await Preferences.get({ key: CHAVE_SESSAO_TOKEN });
    if (!token) return;
    localStorage.setItem(CHAVE_SESSAO_TOKEN, token);
    localStorage.setItem("manter_conectado", "1"); // só existe cópia nativa para sessões "manter conectado"
    const { value: usuario } = await Preferences.get({ key: CHAVE_SESSAO_USUARIO });
    if (usuario) localStorage.setItem(CHAVE_SESSAO_USUARIO, usuario);
    const { value: fazenda } = await Preferences.get({ key: CHAVE_SESSAO_FAZENDA });
    if (fazenda) localStorage.setItem(CHAVE_SESSAO_FAZENDA, fazenda);
    const { value: contaAtiva } = await Preferences.get({ key: CHAVE_SESSAO_CONTA_ATIVA });
    if (contaAtiva) localStorage.setItem(CHAVE_SESSAO_CONTA_ATIVA, contaAtiva);
  } catch { /* best-effort */ }
}

/** Limpa a cópia nativa da sessão — chamado no logout (ver lib/api.ts::logout),
 *  senão o próximo login com "Manter conectado" restauraria a sessão antiga
 *  neste mesmo aparelho. Não faz nada fora do app nativo. */
export async function limparSessaoNativa(): Promise<void> {
  if (!(await ehApp())) return;
  try {
    const { Preferences } = await import("@capacitor/preferences");
    await Preferences.remove({ key: CHAVE_SESSAO_TOKEN });
    await Preferences.remove({ key: CHAVE_SESSAO_USUARIO });
    await Preferences.remove({ key: CHAVE_SESSAO_FAZENDA });
    await Preferences.remove({ key: CHAVE_SESSAO_CONTA_ATIVA });
  } catch { /* best-effort */ }
}

/** Registra um callback disparado toda vez que o SISTEMA traz o app de
 *  volta ao primeiro plano — dentro do app nativo usa o evento do próprio
 *  Capacitor (appStateChange), fora dele mas ainda no PWA instalado
 *  (standalone) usa a Page Visibility API do navegador (visibilitychange).
 *  Os dois só disparam quando o FOCO DO SISTEMA OPERACIONAL muda (a pessoa
 *  saiu para outro app/tela inicial/trocou de app e voltou, ou abriu o app
 *  do zero) — NUNCA por navegação interna (trocar de tela dentro do
 *  próprio app), que não mexe no foco do SO. É exatamente essa distinção
 *  que permite perguntar "trocar de conta?" a cada ABERTURA (ver
 *  AuthShell.tsx) sem a pergunta reaparecer a cada troca de aba interna,
 *  o que viraria tortura.
 *
 *  Retorna a função de limpeza. Fora do app nativo/PWA (site comum, onde
 *  esta pergunta não se repete sozinha — ver AuthShell.tsx) não registra
 *  nada e devolve um no-op. */
/** O app de campo (/app) é para CELULAR — esta é a regra única que decide
 * quem cai nele.
 *
 * `ehAppOuPwa()` sozinho não serve: `display-mode: standalone` não tem relação
 * nenhuma com tamanho de tela, então um atalho instalado no notebook responde
 * "sim" igual a um celular. Era por isso que instalar o PWA no computador
 * abria o app de campo, e a pessoa tinha que ir no menu e pedir "site
 * completo" toda vez.
 *
 * App nativo (Capacitor) é sempre celular ou tablet, então entra direto. PWA
 * instalado só entra se a tela também for pequena. Navegador comum (aba) nunca
 * entra — quem quiser o app de campo no desktop navega para /app na mão.
 *
 * A regra nasceu em app/painel-cowdata/layout.tsx (01/09/2026) e valia só
 * lá; aqui ela é o comportamento do produto inteiro. */
export async function ehAppDeCampo(): Promise<boolean> {
  if (await ehApp()) return true;
  if (typeof window === "undefined") return false;
  return (await ehAppOuPwa()) && window.matchMedia("(max-width: 767px)").matches;
}

export async function registrarAoAbrirApp(callback: () => void): Promise<() => void> {
  if (await ehApp()) {
    const { App } = await import("@capacitor/app");
    const handle = await App.addListener("appStateChange", ({ isActive }) => { if (isActive) callback(); });
    return () => { handle.remove(); };
  }
  if (typeof document !== "undefined" && (await ehAppOuPwa())) {
    const ouvinte = () => { if (document.visibilityState === "visible") callback(); };
    document.addEventListener("visibilitychange", ouvinte);
    return () => document.removeEventListener("visibilitychange", ouvinte);
  }
  return () => {};
}
