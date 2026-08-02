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
// ─────────────────────────────────────────────────────────────────────────────
import { useEffect, useMemo, useState } from "react";
import { API, getToken, getFazendaAtual } from "@/lib/api";
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
  if (!navigator.onLine) {
    await inserirItem({ id, criadoEm: new Date().toISOString(), caminho, metodo, corpo, descricao, tipo: "json", status: "pendente", fazendaId: getFazendaAtual()?.id ?? null });
    await recarregarEspelho().catch(() => {}); // notificação best-effort — a operação em si já terminou
    return { enviado: false };
  }
  const { authFetch } = await import("@/lib/api");
  try {
    const res = await authFetch(`${API}${caminho}`, {
      method: metodo,
      headers: { "Content-Type": "application/json", "Idempotency-Key": id },
      body: JSON.stringify(corpo),
      signal: AbortSignal.timeout(TIMEOUT_ENVIO_MS),
    });
    if (!res.ok) {
      const detalhe = await res.json().catch(() => ({}));
      throw new Error(detalhe.detail || `Erro ${res.status} ao salvar`);
    }
    const resposta = await res.json().catch(() => undefined);
    return { enviado: true, resposta };
  } catch (e) {
    // TypeError = falha de REDE (não chegou ao servidor); timeout também
    // aborta como erro de rede, não de validação → nos dois casos, enfileira.
    if (e instanceof TypeError || (e instanceof DOMException && e.name === "AbortError")) {
      await inserirItem({ id, criadoEm: new Date().toISOString(), caminho, metodo, corpo, descricao, tipo: "json", status: "pendente", fazendaId: getFazendaAtual()?.id ?? null });
      await recarregarEspelho().catch(() => {}); // notificação best-effort — a operação em si já terminou
      return { enviado: false };
    }
    throw e; // resposta do servidor (validação etc.) → o formulário mostra
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

  if (!navigator.onLine) {
    if (modoLegado) throw new Error("Este aparelho não consegue guardar fotos offline — tente novamente com internet.");
    if (!(await cabeNoDisco(opcoes.arquivo.size))) throw new ErroCotaOutbox();
    await enfileirarArquivo();
    return { enviado: false };
  }

  const { authFetch } = await import("@/lib/api");
  try {
    const res = await authFetch(`${API}${opcoes.caminho}`, {
      method: metodo,
      body: montarFormData(), // sem Content-Type manual — o browser gera o boundary
      signal: AbortSignal.timeout(TIMEOUT_ENVIO_ARQUIVO_MS),
    });
    if (!res.ok) {
      const detalhe = await res.json().catch(() => ({}));
      throw new Error(detalhe.detail || `Erro ${res.status} ao enviar`);
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
        // lugar errado. Pula (sem contar tentativa) até o usuário voltar
        // pra fazenda certa. `fazendaId` undefined = item antigo (migrado
        // antes deste campo existir) — sincroniza normalmente.
        if (atual.fazendaId !== undefined && atual.fazendaId !== (getFazendaAtual()?.id ?? null)) continue;
        try {
          const res = atual.tipo === "form" ? await fetchCruArquivo(atual) : await fetchCru(atual.caminho, atual.metodo, atual.corpo, atual.id);
          if (res.ok) {
            await removerItem(atual.id);
            enviados++;
            continue;
          }
          if (res.status === 401 || res.status === 403 || res.status >= 500) {
            // Sessão expirada ou servidor fora do ar — tenta de novo mais
            // tarde, nunca descarta nem marca como erro definitivo.
            const tentativas = (atual.tentativas || 0) + 1;
            await atualizarItem(atual.id, { tentativas, proximaTentativaEm: proximaTentativa(tentativas) });
            continue;
          }
          // 4xx "de verdade" (400/404/409/422...) = dado inválido, exige o usuário.
          const detalhe = await res.json().catch(() => ({}));
          await atualizarItem(atual.id, { status: "erro", erro: detalhe.detail || `Erro ${res.status}` });
        } catch (e) {
          // Rede caiu de novo no meio deste grupo — para só este grupo; o
          // próximo (json→form ou form→json) ainda é tentado. Registra a
          // tentativa e a mensagem técnica (diagnóstico só — não bloqueia
          // retentativa) em vez de falhar 100% em silêncio: sem isso, uma
          // falha que se repete sempre (CORS, DNS, URL de API errada) parece
          // idêntica a "nunca tentou", indistinguível pra quem usa o app.
          const tentativas = (atual.tentativas || 0) + 1;
          await atualizarItem(atual.id, {
            tentativas, proximaTentativaEm: proximaTentativa(tentativas),
            debugUltimoErro: e instanceof Error ? `${e.name}: ${e.message}` : String(e),
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
