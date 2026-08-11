"use client";
// ─────────────────────────────────────────────────────────────────────────────
// Infraestrutura offline do app móvel (/app):
//
// 1. useOnline()        — está com internet agora? (bolinha verde/vermelha)
// 2. fetchComCache()    — GET com cache local: online atualiza o cache; sem
//                         internet devolve a última versão vista.
// 3. enviarOuEnfileirar() — POST JSON que, sem internet, entra numa FILA
//                         local (outbox) e é enviado sozinho quando a
//                         conexão volta.
// 4. enviarOuEnfileirarArquivo() — o mesmo, para upload binário (fotos).
// 5. sincronizar()      — percorre a fila e envia; roda no evento 'online',
//                         na abertura do app e periodicamente como garantia.
//
// A fila (outbox) vive no IndexedDB (lib/outboxDb.ts) — guarda tanto
// lançamentos JSON quanto uploads binários (Blob), com um espelho em
// memória (`espelho`) para leitura síncrona (pendentes(), usePendentes()).
// Se o navegador não tiver IndexedDB (raríssimo — modoLegado), a fila cai
// de volta para localStorage, mas SEM suporte a upload de arquivo (não dá
// pra guardar Blob em string com segurança).
//
// Histórico de correções (achados numa revisão de arquitetura — ver conversa):
//   - sincronizar() usava authFetch(), que faz logout() automático em
//     qualquer 401 — inclusive um token expirado NO MEIO da fila, o que
//     derrubava a sessão em silêncio e ainda marcava o item como "erro"
//     permanente (o usuário tinha que "Descartar" um lançamento válido).
//     Agora a fila usa um fetch cru, sem esse efeito colateral, e trata
//     401/403/5xx como "tenta depois" — nunca como erro definitivo (esse
//     fica reservado pra 4xx de validação de dado de verdade).
//   - navigator.onLine mente (Wi-Fi sem internet de verdade, comum em
//     fazenda) — enviarOuEnfileirar só usa isso pra decidir o caminho
//     RÁPIDO; se navigator.onLine disser "online" mas a rede falhar mesmo
//     assim, cai no mesmo tratamento de enfileirar.
//   - Sem timeout: uma rede ruim deixava o fetch pendurado por minutos,
//     travando a tela do formulário. Agora todo envio tem timeout.
//   - Sem backoff: tentava a cada 30s pra sempre, mesmo com o servidor
//     fora do ar. Agora cada item tem sua própria espera crescente.
//   - localStorage não guarda Blob de forma segura e tem cota pequena
//     (~5-10MB) — insuficiente para fotos de câmera. Fila migrada para
//     IndexedDB (ver lib/outboxDb.ts), guardando o Blob por referência.
//   - Item ficava preso em "Aguardando envio…" pra sempre, sem nunca crescer
//     o contador de tentativas nem deixar pista nenhuma do motivo: (1)
//     enviarOuEnfileirar/enviarOuEnfileirarArquivo usavam AbortSignal.timeout()
//     como sinal de abort — API ausente em WebView Android desatualizada,
//     que lança TypeError antes do fetch sequer sair, tratado (de propósito)
//     como falha de rede → trocado pelo padrão manual (AbortController +
//     setTimeout) já usado em fetchCru, que funciona em qualquer WebView.
//     (2) o catch genérico do loop de sincronizar() e o `continue` do filtro
//     de fazenda engoliam o erro sem logar nem contar tentativa — agora
//     ambos logam (console.error/warn, visível via chrome://inspect — já
//     ligado, ver capacitor.config.ts) e incrementam tentativas com o mesmo
//     backoff dos outros ramos, só pra tornar o retry visível (não muda o
//     design de nunca marcar erro definitivo por falha de rede).
//   - "onLine=true rede=4g 9.5Mbps" no debugUltimoErro (diagnóstico da
//     correção acima) mostrou um relato real de sincronização travada por
//     dias a fio, sempre com sinal de rádio bom — mas isso só prova que a
//     RÁDIO do aparelho está conectada, nunca que o SERVIDOR está alcançável
//     (DNS/TLS/roteamento até nós pode falhar com sinal ótimo — comum em
//     bloqueio de operadora ou WebView com certificado desatualizado). A
//     bolinha verde/vermelha do cabeçalho do app (`app/app/layout.tsx`)
//     também usava só navigator.onLine, então dizia "conectado" mesmo nesse
//     cenário — dado enganoso bater de frente com "não sincroniza nada".
//     Duas correções: (1) diagnosticoFalhaRede() (abaixo) agora tenta de
//     verdade um GET /health com timeout curto (5s) toda vez que um envio
//     falha por rede, e anota se o SERVIDOR respondeu ou não — separando
//     "sinal bom mas nosso servidor inalcançável" de "falha pontual deste
//     envio só". (2) useConectividadeReal() (abaixo) faz o mesmo ping
//     periódico usado pelo indicador do site desktop (ver Sidebar.tsx) — a
//     bolinha do app agora reflete se o SERVIDOR respondeu, não só a rádio.
// ─────────────────────────────────────────────────────────────────────────────
import { useEffect, useMemo, useState } from "react";
import { API, getToken, getFazendaAtual, mensagemErroApi } from "@/lib/api";
import {
  garantirPronto, pedirStoragePersistente, idbDisponivel, cabeNoDisco,
  inserirRegistro, lerRegistro, listarResumos, atualizarRegistro, removerRegistro, lerBlob,
  ErroCotaOutbox,
  type RegistroOutbox, type ResumoOutbox, type TipoItem,
} from "@/lib/outboxDb";

export { ErroCotaOutbox };

const CHAVE_OUTBOX_LEGADO = "mob_outbox"; // só usado em modoLegado (IndexedDB indisponível)
const PREFIXO_CACHE = "mob_cache_";
export const EVENTO_OUTBOX = "mob-outbox-mudou";

// Timeout de rede — rede rural ruim não pode travar a tela pendurada.
const TIMEOUT_ENVIO_MS = 12000;
// Upload binário (fotos) pode levar bem mais tempo em 3G rural (2-8 MB).
const TIMEOUT_ENVIO_ARQUIVO_MS = 120000;
// Backoff por item: 30s, 60s, 120s, 240s, teto de 5min. Evita martelar um
// servidor fora do ar ou um token que não vai se renovar sozinho.
const BACKOFF_BASE_MS = 30000;
const BACKOFF_TETO_MS = 5 * 60000;

/** Compatibilidade com o formato antigo — todo consumidor existente (Menu,
 *  cabeçalho do app) só lê descricao/criadoEm/erro/tentativas/id, que
 *  continuam presentes; os campos novos (tipo/status/arquivo) são extras. */
export type ItemOutbox = ResumoOutbox;

let canal: BroadcastChannel | null = null;
if (typeof window !== "undefined" && "BroadcastChannel" in window) {
  try { canal = new BroadcastChannel("mob-outbox"); } catch { canal = null; }
}

function notificarMudanca() {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(EVENTO_OUTBOX));
  try { canal?.postMessage("mudou"); } catch { /* ignore */ }
}

function gerarId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

// ── Inicialização (IndexedDB, com fallback pra localStorage) ────────────────
let modoLegado = false;
let inicializado: Promise<void> | null = null;

/** Garante que o outbox está pronto (abre/migra o IndexedDB). Se o
 *  navegador não tiver IndexedDB (ou a abertura falhar por algum motivo),
 *  cai para localStorage — só JSON, sem upload de arquivo (ver
 *  enviarOuEnfileirarArquivo abaixo). Memoizado: roda uma única vez. */
function iniciar(): Promise<void> {
  if (!inicializado) {
    inicializado = (async () => {
      if (!idbDisponivel()) { modoLegado = true; return; }
      try { await garantirPronto(); } catch { modoLegado = true; }
    })();
  }
  return inicializado;
}

// ── Modo legado (só localStorage, sem Blob) ──────────────────────────────────
function pendentesLegado(): RegistroOutbox[] {
  try { return JSON.parse(localStorage.getItem(CHAVE_OUTBOX_LEGADO) || "[]"); } catch { return []; }
}
function gravarLegado(fila: RegistroOutbox[]) {
  try { localStorage.setItem(CHAVE_OUTBOX_LEGADO, JSON.stringify(fila)); } catch { /* cheio */ }
}

// ── Espelho em memória — leitura síncrona (pendentes(), usePendentes()) ─────
let espelho: ItemOutbox[] = [];

async function listarTudo(): Promise<ResumoOutbox[]> {
  if (modoLegado) return pendentesLegado();
  return listarResumos();
}

async function recarregarEspelho(): Promise<void> {
  espelho = await listarTudo();
  notificarMudanca();
}

async function inserirItem(reg: RegistroOutbox): Promise<void> {
  if (modoLegado) { gravarLegado([...pendentesLegado(), reg]); return; }
  await inserirRegistro(reg);
}
async function atualizarItem(id: string, patch: Partial<RegistroOutbox>): Promise<void> {
  if (modoLegado) { gravarLegado(pendentesLegado().map((i) => (i.id === id ? { ...i, ...patch } : i))); return; }
  await atualizarRegistro(id, patch);
}
async function removerItem(id: string): Promise<void> {
  if (modoLegado) { gravarLegado(pendentesLegado().filter((i) => i.id !== id)); return; }
  await removerRegistro(id);
}
async function lerItemCompleto(id: string): Promise<RegistroOutbox | null> {
  if (modoLegado) return pendentesLegado().find((i) => i.id === id) ?? null;
  return lerRegistro(id);
}

// ── Conectividade ────────────────────────────────────────────────────────────
export function useOnline(): boolean {
  const [online, setOnline] = useState(true);
  useEffect(() => {
    setOnline(navigator.onLine);
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => { window.removeEventListener("online", on); window.removeEventListener("offline", off); };
  }, []);
  return online;
}

/** Diferente de useOnline() (rádio do aparelho, pode mentir) — pinga de
 *  verdade GET /health, mesmo padrão já usado no indicador do site desktop
 *  (ver Sidebar.tsx). Usado na bolinha do cabeçalho do app (app/app/layout.tsx)
 *  pra ela parar de dizer "conectado" quando o aparelho tem rádio mas nosso
 *  servidor está inalcançável — exatamente o cenário que confundia o
 *  diagnóstico de "sincronização não funciona" (rádio bom, bolinha verde,
 *  mas nada sincroniza). Otimista (`true`) até a 1ª checagem responder, pra
 *  não piscar vermelho no instante de abrir o app. */
export function useConectividadeReal(): boolean {
  const [online, setOnline] = useState(true);
  useEffect(() => {
    let ativo = true;
    const checar = () => probarServidorAlcancavel().then((ok) => { if (ativo) setOnline(ok); });
    checar();
    const id = setInterval(checar, 30000);
    return () => { ativo = false; clearInterval(id); };
  }, []);
  return online;
}

// ── Cache de leitura (GET) ───────────────────────────────────────────────────
export async function fetchComCache<T>(chave: string, buscar: () => Promise<T>): Promise<{ dados: T | null; doCache: boolean }> {
  try {
    const dados = await buscar();
    try { localStorage.setItem(PREFIXO_CACHE + chave, JSON.stringify({ dados, em: new Date().toISOString() })); } catch { /* cheio */ }
    return { dados, doCache: false };
  } catch {
    try {
      const raw = localStorage.getItem(PREFIXO_CACHE + chave);
      if (raw) return { dados: (JSON.parse(raw).dados as T), doCache: true };
    } catch { /* ignore */ }
    return { dados: null, doCache: true };
  }
}

/** Momento da última cópia local de uma chave de cache (ou null). */
export function cacheEm(chave: string): string | null {
  try { const raw = localStorage.getItem(PREFIXO_CACHE + chave); return raw ? JSON.parse(raw).em : null; } catch { return null; }
}

/** Leitura síncrona só dos dados de uma chave de cache (sem buscar nada nem
 *  tocar rede) — mesmo esquema de chave/prefixo e mesmo formato salvo por
 *  fetchComCache ({ dados, em }). Usado para estatísticas ao vivo (ex.: Menu)
 *  que reaproveitam um cache já escrito por outra tela, sem custar requisição
 *  nova. Null tanto se a chave nunca foi salva quanto se o JSON está corrompido. */
export function lerCache<T>(chave: string): T | null {
  try {
    const raw = localStorage.getItem(PREFIXO_CACHE + chave);
    if (!raw) return null;
    return (JSON.parse(raw).dados as T) ?? null;
  } catch {
    return null;
  }
}

// ── Fila de envio (outbox) — leitura ─────────────────────────────────────────
/** Snapshot síncrono do espelho em memória — vazio até a primeira hidratação
 *  (que acontece ~logo após o mount de usePendentes() ou de
 *  iniciarSincronizacaoAutomatica()). Para um valor sempre fresco, use
 *  pendentesAsync(). */
export function pendentes(): ItemOutbox[] {
  return espelho;
}

export async function pendentesAsync(): Promise<ItemOutbox[]> {
  await iniciar();
  await recarregarEspelho().catch(() => {}); // notificação best-effort — a operação em si já terminou
  return espelho;
}

export async function descartarPendente(id: string): Promise<void> {
  await iniciar();
  await removerItem(id);
  await recarregarEspelho().catch(() => {}); // notificação best-effort — a operação em si já terminou
}

/** Bytes de um item pendente ainda não enviado (ex.: miniatura de uma foto
 *  na própria tela onde foi tirada). O chamador é dono do objectURL que
 *  criar a partir do Blob (precisa dar URL.revokeObjectURL ao descartar). */
export async function lerArquivoPendente(id: string): Promise<Blob | null> {
  await iniciar();
  if (modoLegado) return null;
  return lerBlob(id);
}

// ── Envio (interativo, em primeiro plano) ────────────────────────────────────
function proximaTentativa(tentativas: number): string {
  const espera = Math.min(BACKOFF_BASE_MS * Math.pow(2, tentativas), BACKOFF_TETO_MS);
  return new Date(Date.now() + espera).toISOString();
}

// Timeout curto — só para o probe de diagnóstico abaixo, nunca deve
// pendurar o loop de sincronização esperando por ele.
const TIMEOUT_PROBE_MS = 5000;

/** GET /health com timeout curto — só para diagnóstico (nunca decide se
 *  enfileira ou não; isso continua vindo do fetch real do próprio envio).
 *  `false` tanto para falha de rede quanto para timeout quanto para
 *  resposta não-2xx — qualquer um desses já significa "não dá pra dizer que
 *  o servidor está alcançável agora". */
async function probarServidorAlcancavel(): Promise<boolean> {
  const controlador = new AbortController();
  const timeoutId = setTimeout(() => controlador.abort(), TIMEOUT_PROBE_MS);
  try {
    const res = await fetch(`${API}/health`, { cache: "no-store", signal: controlador.signal });
    return res.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timeoutId);
  }
}

/** Diagnóstico do momento da falha — anexado à mensagem técnica
 *  (debugUltimoErro) pra separar "sem sinal de verdade" de "tem sinal mas o
 *  fetch falhou mesmo assim" (ex.: WebView com problema, DNS, certificado) —
 *  sem isso, "TypeError: Failed to fetch" sozinho não diz qual dos dois é,
 *  e foi exatamente essa dúvida que travou o diagnóstico de um relato real
 *  ("app não envia dados", com sinal 4G bom informado pelo próprio
 *  aparelho). navigator.connection só existe em Chrome/WebView Android —
 *  undefined em iOS/Safari, ok ficar de fora nesse caso. Além do sinal de
 *  rádio (que só prova que a operadora está conectada, nunca que NOSSO
 *  servidor está alcançável), tenta de verdade um GET /health com timeout
 *  curto — se ele TAMBÉM falhar, é bloqueio/instabilidade de rede até o
 *  servidor (DNS, TLS, operadora), não uma falha pontual deste envio. */
async function diagnosticoFalhaRede(): Promise<string> {
  const partes: string[] = [`onLine=${typeof navigator !== "undefined" ? navigator.onLine : "?"}`];
  const conexao = typeof navigator !== "undefined" ? (navigator as any).connection : undefined;
  if (conexao) {
    partes.push(`rede=${conexao.effectiveType ?? "?"}`);
    if (typeof conexao.downlink === "number") partes.push(`${conexao.downlink}Mbps`);
    if (conexao.saveData) partes.push("economiaDeDados=on");
  }
  const servidorAlcancavel = await probarServidorAlcancavel();
  partes.push(
    servidorAlcancavel
      ? "servidorRespondeu=sim(provável falha pontual só deste envio)"
      : "servidorRespondeu=NÃO(nosso servidor está inalcançável a partir daqui, mesmo com sinal — não é só sinal fraco)",
  );
  return partes.join(" ");
}

// ── Fallback: ponte nativa CapacitorHttp() chamada DIRETO ──────────────────
// Prova real (revisão de código, ago/2026 — ver node_modules/@capacitor/
// android/capacitor/src/main/assets/native-bridge.js e .../plugin/
// CapacitorHttp.java, .../PluginCall.java): capacitor.config.ts já liga
// `CapacitorHttp: { enabled: true }` pra fazer window.fetch/XMLHttpRequest
// passarem pela ponte nativa (OkHttp) em vez do fetch cru da WebView — mas
// essa flag só produz efeito quando ela realmente chega ao .apk instalado
// no aparelho (exige `npx cap sync android` refletido no build + o
// funcionário ter reinstalado essa versão; a flag mora em
// android/app/src/main/assets/capacitor.config.json, um arquivo GERADO,
// fora do git). Se o aparelho ainda roda um .apk mais velho que a
// correção, ou o sync nunca rodou antes do build, window.fetch nunca foi
// trocado e continua sendo o fetch cru da própria Android System WebView —
// e o relato real da fila travada prova exatamente isso: o erro capturado
// é literalmente "TypeError: Failed to fetch", o texto de erro de rede do
// PRÓPRIO Chromium (blink). Quando a ponte nativa de verdade falha, o erro
// que ela devolve pro JS tem `.name` "Error" (CapacitorException, sem
// override de name — ver PluginCall.java `reject()`) e `.message` = a
// mensagem da exception Java (ex.: "Unable to resolve host…") — NUNCA
// "TypeError: Failed to fetch". Ou seja: essa string por si só já é a prova
// de que a requisição que falhou não passou pela ponte nativa.
// Em vez de confiar de novo só na flag automática (que já devia estar
// ligada e não resolveu o relato), as funções de envio abaixo chamam o
// plugin CapacitorHttp DIRETO — `CapacitorHttp.request()` — como ÚLTIMA
// tentativa depois que o fetch normal já falhou por rede. Funciona mesmo
// que o patch automático de window.fetch nunca tenha entrado em vigor,
// porque o Android registra o plugin CapacitorHttp incondicionalmente
// (Bridge.java, no construtor da Bridge — a flag "enabled" só liga o PATCH
// automático de fetch/XHR, não a existência do plugin em si). Nunca roda
// fora do app nativo (PWA/Chrome não têm ponte nenhuma — Capacitor.
// isNativePlatform() volta false, e a função desiste rápido) — o
// comportamento do PWA não muda em nada.
let capacitorCoreCache: typeof import("@capacitor/core") | null = null;
async function carregarPonteNativa(): Promise<typeof import("@capacitor/core") | null> {
  if (typeof window === "undefined") return null;
  try {
    if (!capacitorCoreCache) capacitorCoreCache = await import("@capacitor/core");
    return capacitorCoreCache.Capacitor.isNativePlatform() ? capacitorCoreCache : null;
  } catch {
    return null; // @capacitor/core ausente (não deveria acontecer dentro do app) — não pode derrubar o envio por isso
  }
}

/** Só o suficiente de `Response` que o resto do código usa (`ok`, `status`,
 *  `json()`) — o mesmo formato serve pra resposta de verdade do fetch da
 *  WebView e pra resposta "traduzida" da ponte nativa abaixo. */
type RespostaEnvio = { ok: boolean; status: number; json: () => Promise<any> };

/** Chama CapacitorHttp.request() direto (sem passar por window.fetch — ver
 *  comentário grande acima). RESOLVE normalmente pra qualquer resposta HTTP
 *  de verdade, mesmo 4xx/5xx (igual o fetch resolveria) — só LANÇA quando a
 *  ponte não existe aqui (fora do app Android) ou quando ela mesma falha de
 *  rede (aí sim equivalente a um TypeError de fetch). */
async function fetchViaPonteNativa(caminho: string, metodo: string, headers: Record<string, string>, corpo: unknown, timeoutMs: number): Promise<RespostaEnvio> {
  const cap = await carregarPonteNativa();
  if (!cap) throw new Error("ponte nativa indisponível aqui (fora do app Android, ou @capacitor/core não carregou)");
  const nativa = await cap.CapacitorHttp.request({
    url: `${API}${caminho}`, method: metodo, headers, data: corpo,
    connectTimeout: timeoutMs, readTimeout: timeoutMs,
  });
  return {
    ok: nativa.status >= 200 && nativa.status < 300,
    status: nativa.status,
    // dataType não foi informado no request acima → o Android decide sozinho
    // a partir do Content-Type da RESPOSTA; nativeResponse.data já vem
    // objeto quando é JSON, mas alguns servidores/erro devolvem texto cru —
    // tenta os dois em vez de assumir um formato só.
    json: async () => (typeof nativa.data === "string" ? JSON.parse(nativa.data) : nativa.data),
  };
}

/** Headers comuns aos dois caminhos de envio JSON (fetch da WebView e ponte
 *  nativa) — Idempotency-Key + Authorization (quando logado). Content-Type
 *  é responsabilidade de quem monta a chamada (aqui sempre application/json). */
function headersEnvioJson(id: string): Record<string, string> {
  const token = getToken();
  return { "Content-Type": "application/json", "Idempotency-Key": id, ...(token ? { Authorization: `Bearer ${token}` } : {}) };
}

/** Interpreta uma RespostaEnvio (de qualquer um dos dois caminhos) do mesmo
 *  jeito que o resto do arquivo sempre interpretou `res` do fetch: 2xx vira
 *  o corpo JSON já decodificado, qualquer outro status vira Error com a
 *  mensagem de validação do backend (mensagemErroApi) — usado tanto pela
 *  tentativa via WebView quanto pela tentativa via ponte nativa, pra não
 *  duplicar essa lógica duas vezes. */
async function resolverRespostaJson(res: RespostaEnvio, mensagemErroPadrao: string): Promise<any> {
  if (!res.ok) {
    const detalhe = await res.json().catch(() => ({}));
    throw new Error(mensagemErroApi(detalhe.detail) || mensagemErroPadrao);
  }
  return res.json().catch(() => undefined);
}

/**
 * Tenta enviar agora; sem internet (ou falha de rede), guarda na fila para
 * sincronizar depois. Erro do servidor (4xx/5xx) com internet É repassado —
 * significa dado inválido, e o usuário deve corrigir na hora.
 * Retorna { enviado } para a tela dizer "salvo" ou "guardado para enviar".
 * `resposta` traz o corpo JSON só quando `enviado` for true (enviou de
 * verdade, na hora) — permite a quem chamou conferir o resultado real antes
 * de comemorar (ex.: `/movimentacoes/mover` devolve `{ movidos, nao_encontrados }`
 * e um 200 não significa necessariamente que o animal foi movido — mesma
 * checagem feita em criarMovimentacao/FormParto). Quando cai na fila
 * (offline), não tem como saber o resultado ainda, então vem undefined.
 */
export async function enviarOuEnfileirar(caminho: string, corpo: unknown, descricao: string, metodo: "POST" | "PUT" | "DELETE" = "POST"): Promise<{ enviado: boolean; resposta?: any }> {
  await iniciar();
  // Gerado ANTES da tentativa (não só ao enfileirar) — vira o header
  // Idempotency-Key tanto na 1ª tentativa quanto em qualquer reenvio pela
  // fila. Isso cobre o caso em que o POST chegou e foi processado no
  // servidor, mas a resposta se perdeu na volta (queda de conexão): o
  // cliente vê erro de rede e enfileira, porém o reenvio usa a MESMA chave,
  // então o servidor devolve a resposta já salva em vez de duplicar.
  const id = gerarId();
  // NÃO trava em navigator.onLine (mesmo motivo de sincronizar() — em WebView
  // Android essa API é conhecida por ficar presa em `false` mesmo com
  // internet real, o que fazia todo lançamento cair direto na fila sem nem
  // tentar enviar, mesmo com internet de verdade). Tenta de verdade; falha de
  // rede cai no catch abaixo e enfileira do mesmo jeito.
  const { authFetch } = await import("@/lib/api");
  // AbortController manual em vez de AbortSignal.timeout() — a API estática
  // só existe em WebView/Chrome 103+ (meados de 2022); num Android System
  // WebView desatualizado (comum em aparelho de uso rural) ela lança um
  // TypeError IMEDIATO, antes do fetch sequer começar, que o catch abaixo
  // trata como falha de rede — enfileirando uma ação que na real tinha
  // internet disponível. O padrão manual (igual ao já usado em fetchCru,
  // abaixo) funciona em qualquer WebView.
  const controlador = new AbortController();
  const timeoutId = setTimeout(() => controlador.abort(), TIMEOUT_ENVIO_MS);
  try {
    const res = await authFetch(`${API}${caminho}`, {
      method: metodo,
      headers: { "Content-Type": "application/json", "Idempotency-Key": id },
      body: JSON.stringify(corpo),
      signal: controlador.signal,
    });
    const resposta = await resolverRespostaJson(res, `Erro ${res.status} ao salvar`);
    return { enviado: true, resposta };
  } catch (e) {
    // TypeError = falha de REDE (não chegou ao servidor); timeout também
    // aborta como erro de rede, não de validação → nos dois casos, enfileira
    // — mas ANTES de desistir, tenta UMA vez a ponte nativa CapacitorHttp
    // direto (ver fetchViaPonteNativa, acima): cobre o caso real (ago/2026)
    // em que window.fetch não estava de fato interceptado pela ponte nativa
    // — mesmo com CapacitorHttp:{enabled:true} escrito em capacitor.config.ts
    // — porque a flag só produz efeito no .apk que foi de fato sincronizado
    // e reinstalado com ela. Se a ponte devolver uma resposta de VERDADE do
    // servidor (2xx ou 4xx/5xx), essa resposta vale tanto quanto a do fetch
    // normal teria valido — inclusive erro de validação (4xx) vai pro
    // formulário na hora, não pra fila (por isso resolverRespostaJson roda
    // dentro do try: um `throw` aí sai deste catch sem cair no `if` abaixo).
    if (e instanceof TypeError || (e instanceof DOMException && e.name === "AbortError")) {
      try {
        const res2 = await fetchViaPonteNativa(caminho, metodo, headersEnvioJson(id), corpo, TIMEOUT_ENVIO_MS);
        const resposta = await resolverRespostaJson(res2, `Erro ${res2.status} ao salvar`);
        return { enviado: true, resposta };
      } catch (e2) {
        // e2 pode ser (a) a ponte nativa também falhando de rede, (b) ela
        // nem existir aqui (PWA/navegador — nunca é o caso na prática, já
        // que só chegamos aqui dentro do app), ou (c) uma resposta de
        // validação do servidor VIA PONTE (Error comum, não TypeError) — só
        // esse último caso deve furar o enfileiramento e ir pro formulário,
        // exatamente como aconteceria se o fetch normal tivesse recebido a
        // mesma resposta.
        if (e2 instanceof Error && !(e2 instanceof TypeError)) {
          const éFalhaDeTransporteDaPonte = e2.message.startsWith("ponte nativa indisponível");
          if (!éFalhaDeTransporteDaPonte) throw e2; // validação de verdade, vinda da ponte — repassa pro formulário
        }
        const motivoWebview = e instanceof Error ? `${e.name}: ${e.message}` : String(e);
        const motivoPonte = e2 instanceof Error ? `${e2.name}: ${e2.message}` : String(e2);
        await inserirItem({
          id, criadoEm: new Date().toISOString(), caminho, metodo, corpo, descricao, tipo: "json", status: "pendente",
          fazendaId: getFazendaAtual()?.id ?? null,
          debugUltimoErro: `[webview] ${motivoWebview} | [ponteNativa] ${motivoPonte} (${await diagnosticoFalhaRede()})`,
        });
        await recarregarEspelho().catch(() => {}); // notificação best-effort — a operação em si já terminou
        return { enviado: false };
      }
    }
    throw e; // resposta do servidor (validação etc.) → o formulário mostra
  } finally {
    clearTimeout(timeoutId);
  }
}

/**
 * Igual a enviarOuEnfileirar, para upload binário (multipart/form-data) —
 * hoje usado pela captura de fotos do campo (POST /fotos/upload). `campos`
 * vira os campos de texto do multipart (ex.: descricao, identificacao_animal
 * — usar EXATAMENTE os nomes que o backend espera); `arquivo` é o Blob/File
 * da foto em si.
 *
 * Sem internet (ou falha de rede), a foto entra na fila do IndexedDB e é
 * enviada sozinha quando a conexão voltar — igual a um lançamento JSON.
 * Lança ErroCotaOutbox se o aparelho não tiver espaço, ou Error comum se o
 * servidor recusou com o app online (dado inválido).
 *
 * Diferente de enviarOuEnfileirar, NÃO tenta a ponte nativa (CapacitorHttp.
 * request()) como fallback aqui: a API nativa exige o arquivo em base64
 * (~33% maior que o Blob original — pesado pra foto de câmera de vários MB
 * em 3G rural, ver convertFormData em native-bridge.js) e o multipart
 * (`dataType: 'formData'`) exigiria remontar cada campo manualmente. Fica
 * só no fetch/FormData de sempre — se a ponte nativa realmente não estiver
 * ativa (ver comentário grande em fetchViaPonteNativa, acima), a foto ainda
 * assim entra na fila normalmente e é reenviada depois; só não ganha a
 * segunda tentativa imediata que o lançamento JSON ganha.
 */
export async function enviarOuEnfileirarArquivo(opcoes: {
  caminho: string;
  descricao: string;
  arquivo: Blob;
  nomeArquivo?: string;
  campoArquivo?: string;
  campos?: Record<string, string | undefined>;
  metodo?: "POST" | "PUT";
}): Promise<{ enviado: boolean }> {
  await iniciar();
  const nomeArquivo = opcoes.nomeArquivo || "arquivo.jpg";
  const campoArquivo = opcoes.campoArquivo || "file";
  const metodo = opcoes.metodo || "POST";
  const camposLimpos: Record<string, string> = {};
  for (const [k, v] of Object.entries(opcoes.campos || {})) if (v !== undefined) camposLimpos[k] = v;

  const montarFormData = () => {
    const fd = new FormData();
    for (const [k, v] of Object.entries(camposLimpos)) fd.append(k, v);
    fd.append(campoArquivo, opcoes.arquivo, nomeArquivo);
    return fd;
  };

  // NÃO trava em navigator.onLine — mesmo motivo de enviarOuEnfileirar/
  // sincronizar() acima: em WebView Android essa API pode ficar presa em
  // `false` mesmo com internet real. Tenta de verdade; falha de rede cai no
  // catch abaixo e enfileira do mesmo jeito.
  const { authFetch } = await import("@/lib/api");
  // Mesmo motivo do AbortController manual em enviarOuEnfileirar (acima):
  // AbortSignal.timeout() não existe em WebView antiga.
  const controlador = new AbortController();
  const timeoutId = setTimeout(() => controlador.abort(), TIMEOUT_ENVIO_ARQUIVO_MS);
  try {
    const res = await authFetch(`${API}${opcoes.caminho}`, {
      method: metodo,
      body: montarFormData(), // sem Content-Type manual — o browser gera o boundary
      signal: controlador.signal,
    });
    if (!res.ok) {
      const detalhe = await res.json().catch(() => ({}));
      throw new Error(mensagemErroApi(detalhe.detail) || `Erro ${res.status} ao enviar`);
    }
    return { enviado: true };
  } catch (e) {
    if (e instanceof TypeError || (e instanceof DOMException && e.name === "AbortError")) {
      if (modoLegado) throw new Error("Este aparelho não consegue guardar fotos offline — tente novamente com internet.");
      if (!(await cabeNoDisco(opcoes.arquivo.size))) throw new ErroCotaOutbox();
      await enfileirarArquivo();
      return { enviado: false };
    }
    throw e;
  } finally {
    clearTimeout(timeoutId);
  }

  async function enfileirarArquivo() {
    await inserirItem({
      id: gerarId(), criadoEm: new Date().toISOString(), descricao: opcoes.descricao,
      caminho: opcoes.caminho, metodo, tipo: "form", status: "pendente",
      fazendaId: getFazendaAtual()?.id ?? null,
      corpo: camposLimpos,
      arquivo: { campo: campoArquivo, nome: nomeArquivo, mime: opcoes.arquivo.type || "application/octet-stream", tamanho: opcoes.arquivo.size, blob: opcoes.arquivo },
    });
    await recarregarEspelho().catch(() => {}); // notificação best-effort — a operação em si já terminou
  }
}

// ── Envio (sincronização em segundo plano) ──────────────────────────────────
// fetch cru com timeout — sem Authorization automático de mais, sem logout
// automático em 401. Usado só pelo caminho de sincronização em background;
// o envio interativo (enviarOuEnfileirar*, com o app em primeiro plano)
// continua usando authFetch de propósito — se o token caiu ali, faz sentido
// mandar pro login na hora, é uma ação que o usuário está vendo acontecer.
async function fetchCru(caminho: string, metodo: string, corpo: unknown, id: string): Promise<Response> {
  const token = getToken();
  const controlador = new AbortController();
  const timeoutId = setTimeout(() => controlador.abort(), TIMEOUT_ENVIO_MS);
  try {
    return await fetch(`${API}${caminho}`, {
      method: metodo,
      // Idempotency-Key = o próprio id do item da fila — reusado em toda
      // tentativa de reenvio (nunca gerado de novo aqui), pra bater com a
      // chave da 1ª tentativa em enviarOuEnfileirar.
      headers: { "Content-Type": "application/json", "Idempotency-Key": id, ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify(corpo),
      cache: "no-store",
      signal: controlador.signal,
    });
  } finally {
    clearTimeout(timeoutId);
  }
}

/** fetchCru + fallback pela ponte nativa (ver comentário grande em
 *  fetchViaPonteNativa, na seção de envio interativo, acima) — mesmo
 *  raciocínio, aplicado ao reenvio em segundo plano: cada rodada de
 *  sincronizar() que falhar por rede tenta a ponte nativa direto ANTES de
 *  desistir e reagendar o backoff, o que é especialmente valioso aqui — é
 *  esse loop que produz o "tentativa 12" do relato real, e cada tentativa
 *  adicional pela ponte é uma chance de recuperar sem esperar o usuário
 *  reinstalar o app. Só para itens `tipo: "json"` (ver fetchCruArquivo,
 *  sem fallback, pelo mesmo motivo do comentário em
 *  enviarOuEnfileirarArquivo). Lança um erro combinado (com os dois motivos
 *  etiquetados) quando AMBOS os caminhos falham, pra debugUltimoErro em
 *  sincronizar() carregar o diagnóstico completo. */
async function fetchCruComFallbackNativo(caminho: string, metodo: string, corpo: unknown, id: string): Promise<RespostaEnvio> {
  try {
    return await fetchCru(caminho, metodo, corpo, id);
  } catch (e) {
    if (!(e instanceof TypeError || (e instanceof DOMException && e.name === "AbortError"))) throw e;
    try {
      return await fetchViaPonteNativa(caminho, metodo, headersEnvioJson(id), corpo, TIMEOUT_ENVIO_MS);
    } catch (e2) {
      const motivoWebview = e instanceof Error ? `${e.name}: ${e.message}` : String(e);
      const motivoPonte = e2 instanceof Error ? `${e2.name}: ${e2.message}` : String(e2);
      throw new Error(`[webview] ${motivoWebview} | [ponteNativa] ${motivoPonte}`);
    }
  }
}

async function fetchCruArquivo(reg: RegistroOutbox): Promise<Response> {
  const token = getToken();
  const controlador = new AbortController();
  const timeoutId = setTimeout(() => controlador.abort(), TIMEOUT_ENVIO_ARQUIVO_MS);
  try {
    const fd = new FormData();
    const corpo = (reg.corpo as Record<string, string>) || {};
    for (const [k, v] of Object.entries(corpo)) fd.append(k, v);
    if (reg.arquivo) fd.append(reg.arquivo.campo, reg.arquivo.blob, reg.arquivo.nome);
    return await fetch(`${API}${reg.caminho}`, {
      method: reg.metodo,
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      body: fd, // sem Content-Type manual — o browser gera o boundary
      cache: "no-store",
      signal: controlador.signal,
    });
  } finally {
    clearTimeout(timeoutId);
  }
}

let sincronizando = false;

/** Envia a fila em ordem — lançamentos JSON primeiro, depois fotos: uma foto
 *  de vários MB com sinal ruim (timeout de até 2min) não pode atrasar um
 *  lançamento reprodutivo/sanitário pendente. Falha de rede/401/403/5xx =
 *  "tenta depois" (nunca grava erro nem desloga) — só 4xx de validação de
 *  dado vira `erro` visível em Menu > Sincronização, exigindo decisão do
 *  usuário. Uma falha de rede pausa só o GRUPO atual (json ou form); o outro
 *  grupo ainda é tentado nesta mesma rodada. */
export async function sincronizar(): Promise<{ enviados: number; restantes: number }> {
  await iniciar();
  // NÃO trava em navigator.onLine aqui — em WebView Android essa API é
  // conhecida por ficar presa em `false` mesmo com internet real (não há
  // garantia de que os eventos 'online'/'offline' disparem de volta), o que
  // travava a fila para sempre (tentativas nunca passava de 0, nenhum erro
  // visível). Tenta de verdade; se estiver offline mesmo, o fetch falha
  // rápido (dentro do timeout) e cai no backoff normal — mesmo resultado,
  // sem o risco de nunca tentar.
  if (sincronizando) return { enviados: 0, restantes: (await listarTudo()).length };
  sincronizando = true;
  let enviados = 0;
  try {
    const agora = Date.now();
    const elegiveis = (await listarTudo()).filter(
      (i) => i.status !== "erro" && (!i.proximaTentativaEm || new Date(i.proximaTentativaEm).getTime() <= agora),
    );
    const grupos: ResumoOutbox[][] = [
      elegiveis.filter((i) => i.tipo === "json"),
      elegiveis.filter((i) => i.tipo === "form"),
    ];
    for (const grupo of grupos) {
      for (const item of grupo) {
        const atual = await lerItemCompleto(item.id);
        if (!atual) continue; // descartado/enviado por outra aba desde a listagem
        // Item enfileirado numa fazenda e o usuário trocou de fazenda antes
        // de sincronizar — o backend grava na fazenda do TOKEN vigente, não
        // na de quando o item foi criado, então enviar agora gravaria no
        // lugar errado. Pula até o usuário voltar pra fazenda certa — mas
        // conta como tentativa (com log) pra não travar em "Aguardando
        // envio…" sem nenhuma pista. `fazendaId` undefined = item antigo
        // (migrado antes deste campo existir) — sincroniza normalmente.
        if (atual.fazendaId !== undefined && atual.fazendaId !== (getFazendaAtual()?.id ?? null)) {
          console.warn(`[offline] sincronizar: pulando "${atual.descricao}" (id ${atual.id}) — fazenda do item (${atual.fazendaId}) difere da atual (${getFazendaAtual()?.id ?? null}).`);
          const tentativas = (atual.tentativas || 0) + 1;
          await atualizarItem(atual.id, { tentativas, proximaTentativaEm: proximaTentativa(tentativas) });
          continue;
        }
        try {
          const res = atual.tipo === "form" ? await fetchCruArquivo(atual) : await fetchCruComFallbackNativo(atual.caminho, atual.metodo, atual.corpo, atual.id);
          if (res.ok) {
            await removerItem(atual.id);
            enviados++;
            continue;
          }
          if (res.status === 401 || res.status === 403 || res.status >= 500) {
            // Sessão expirada ou servidor fora do ar — tenta de novo mais
            // tarde, nunca descarta nem marca como erro definitivo. Mas
            // registra o motivo em debugUltimoErro (igual ao catch abaixo):
            // sem isso, um token expirado ficava pendurado indefinidamente
            // como "pendente", sem nenhuma pista visível na tela de
            // Sincronização de por que nunca ia embora (relato: "app não
            // envia dados pra nuvem" — a causa mais provável é essa).
            const tentativas = (atual.tentativas || 0) + 1;
            const motivo = res.status === 401 || res.status === 403
              ? "Sessão expirada — abra o app e faça login de novo para este item ser enviado."
              : `Servidor indisponível (${res.status}) — vai tentar de novo automaticamente.`;
            await atualizarItem(atual.id, { tentativas, proximaTentativaEm: proximaTentativa(tentativas), debugUltimoErro: motivo });
            continue;
          }
          // 4xx "de verdade" (400/404/409/422...) = dado inválido, exige o usuário.
          const detalhe = await res.json().catch(() => ({}));
          await atualizarItem(atual.id, { status: "erro", erro: mensagemErroApi(detalhe.detail) || `Erro ${res.status}` });
        } catch (e) {
          // Rede caiu de novo no meio deste grupo — para só este grupo; o
          // próximo (json→form ou form→json) ainda é tentado. Registra a
          // tentativa e a mensagem técnica (diagnóstico só — não bloqueia
          // retentativa) em vez de falhar 100% em silêncio: sem isso, uma
          // falha que se repete sempre (CORS, DNS, URL de API errada) parece
          // idêntica a "nunca tentou", indistinguível pra quem usa o app.
          const tentativas = (atual.tentativas || 0) + 1;
          const motivo = e instanceof Error ? `${e.name}: ${e.message}` : String(e);
          await atualizarItem(atual.id, {
            tentativas, proximaTentativaEm: proximaTentativa(tentativas),
            debugUltimoErro: `${motivo} (${await diagnosticoFalhaRede()})`,
          });
          break;
        }
      }
    }
  } finally {
    sincronizando = false;
    await recarregarEspelho().catch(() => {}); // notificação best-effort — a operação em si já terminou
  }
  return { enviados, restantes: (await listarTudo()).length };
}

/** Hook: quantidade (e lista) de pendentes, atualizada ao vivo. */
export function usePendentes(): ItemOutbox[] {
  const [fila, setFila] = useState<ItemOutbox[]>(espelho);
  useEffect(() => {
    let cancelado = false;
    iniciar().then(() => recarregarEspelho()).then(() => { if (!cancelado) setFila(espelho); }).catch(() => {});
    const ler = () => setFila(espelho);
    window.addEventListener(EVENTO_OUTBOX, ler);
    window.addEventListener("storage", ler); // fallback do modoLegado (localStorage)
    canal?.addEventListener("message", ler);
    return () => {
      cancelado = true;
      window.removeEventListener(EVENTO_OUTBOX, ler);
      window.removeEventListener("storage", ler);
      canal?.removeEventListener("message", ler);
    };
  }, []);
  return fila;
}

/** Igual a usePendentes(), filtrado por tipo (e opcionalmente por rota) —
 *  usado pela tela de Fotos do campo para mostrar só as fotos aguardando
 *  envio, sem duplicar a lógica de fila. */
export function usePendentesDe(tipo: TipoItem, caminho?: string): ItemOutbox[] {
  const todos = usePendentes();
  return useMemo(() => todos.filter((i) => i.tipo === tipo && (!caminho || i.caminho === caminho)), [todos, tipo, caminho]);
}

/** Liga a sincronização automática: ao voltar a internet, ao abrir e
 *  periodicamente como garantia (o backoff de cada item, acima, evita
 *  martelar o servidor — este intervalo só precisa ser curto o bastante
 *  pra sentir a volta da conexão). Também prepara o IndexedDB (abre + migra
 *  itens antigos do localStorage) e pede armazenamento persistente (reduz o
 *  risco do navegador despejar a fila sob pressão de disco). */
export function iniciarSincronizacaoAutomatica(): () => void {
  iniciar().then(() => { pedirStoragePersistente().catch(() => {}); recarregarEspelho().catch(() => {}); });

  const aoConectar = () => { sincronizar(); };
  window.addEventListener("online", aoConectar);
  sincronizar();
  const id = setInterval(() => { sincronizar(); }, 20000);
  return () => { window.removeEventListener("online", aoConectar); clearInterval(id); };
}
