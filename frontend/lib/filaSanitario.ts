"use client";
// Fila do aparelho do Sanitário Preventivo (app de campo).
//
// Reaproveita a fila offline do app (lib/offline.ts + lib/outboxDb.ts:
// IndexedDB, espelho em memória, contador de pendentes do cabeçalho, tela de
// Sincronização, filtro por fazenda, transporte sem logout em 401 e com a
// ponte nativa do Capacitor). Cada registro de vacina/exame entra como um item
// `tipo: "sanitario"` cujo id É a chave de idempotência do registro.
//
// Diferença para os outros lançamentos do app: o envio é em LOTE pelo
// POST /sanitario/campo/sincronizar, e a resposta vem POR REGISTRO
// (gravado / duplicado / conflito / pendente / erro — ver lib/sanitarioCampo.ts
// interpretarSync). Reenviar não duplica (o back confere a chave).
//
// Heartbeat: a cada sincronização e a cada 5 min com o app aberto, o aparelho
// conta ao servidor quantos registros guarda (POST /sanitario/dispositivos/
// heartbeat); o job do servidor avisa o administrador se ele sumir 24 h com
// registros. O próprio app avisa o usuário (filaAtrasada), mesmo sem sinal.
import { useCallback, useEffect, useState } from "react";
import { getFazendaAtual, getToken, getUsuario, mensagemErroApi } from "@/lib/api";
import {
  EVENTO_OUTBOX, atualizarNaFila, inserirNaFila, itensDaFila, maisAntigoDe, postarCru, registrarSincronizador, removerDaFila,
} from "@/lib/offline";
import {
  corpoHeartbeat, corpoSincronizar, decidirItem, filaAtrasada, interpretarSync, juntarResultados,
  type CorpoSan, type RegistroCampo, type ResultadoSan,
} from "@/lib/sanitarioCampo";
import { novaChave, type SincronizarOut } from "@/lib/sanitarioTipos";

export const CAMINHO_SYNC = "/sanitario/campo/sincronizar";
const CAMINHO_HEARTBEAT = "/sanitario/dispositivos/heartbeat";
const CHAVE_UID = "san_dispositivo_uid";
const CHAVE_ATIVO = "san_campo_ativo";
const CHAVE_AVISO_HORAS = "san_aviso_offline_horas";
const PREFIXO_RESULTADOS = "san_resultados_sync_";
const PREFIXO_ULTIMO_OK = "san_ultimo_envio_ok_";
export const EVENTO_SAN = "san-fila-mudou";
const LOTE_MAX = 100;
const BACKOFF_BASE_MS = 30000;
const BACKOFF_TETO_MS = 5 * 60000;
const HEARTBEAT_MS = 5 * 60000;

function ls(): Storage | null {
  try { return typeof window !== "undefined" ? window.localStorage : null; } catch { return null; }
}
function fazendaChave(): string {
  return String(getFazendaAtual()?.id ?? "sem");
}
function emitir() {
  if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent(EVENTO_SAN));
}

// ── aparelho ──
/** Identificador estável deste aparelho (gerado uma vez e guardado). */
export function dispositivoUid(): string {
  const s = ls();
  let uid = s?.getItem(CHAVE_UID) || "";
  if (!uid) {
    uid = novaChave("cel").slice(4);
    try { s?.setItem(CHAVE_UID, uid); } catch { /* sem armazenamento: um uid por sessão */ }
  }
  return uid;
}
/** Nome legível do aparelho para o administrador ("celular do Zé · Android"). */
export function nomeDispositivo(): string {
  const u = getUsuario();
  const quem = (u?.nome || u?.username || "usuário") as string;
  const ua = typeof navigator !== "undefined" ? navigator.userAgent : "";
  const plataforma = /android/i.test(ua) ? "Android" : /iphone|ipad/i.test(ua) ? "iPhone" : "navegador";
  return `Celular de ${quem} · ${plataforma}`;
}
/** Marca que este aparelho usa o sanitário (só então manda heartbeat). */
export function marcarCampoAtivo() {
  try { ls()?.setItem(CHAVE_ATIVO, "1"); } catch { /* ignore */ }
}
function campoAtivo(): boolean {
  return ls()?.getItem(CHAVE_ATIVO) === "1";
}
/** Horas para o aviso local (Parâmetros › Sanitário, vem no pacote offline). */
export function avisoOfflineHoras(): number {
  const n = Number(ls()?.getItem(CHAVE_AVISO_HORAS));
  return Number.isFinite(n) && n >= 1 ? n : 24;
}
export function guardarAvisoOfflineHoras(h: number | null | undefined) {
  if (h && h >= 1) try { ls()?.setItem(CHAVE_AVISO_HORAS, String(h)); } catch { /* ignore */ }
}

// ── resultados da última sincronização (por fazenda) ──
export function lerResultados(): ResultadoSan[] {
  try { return JSON.parse(ls()?.getItem(PREFIXO_RESULTADOS + fazendaChave()) || "[]"); } catch { return []; }
}
function gravarResultados(r: ResultadoSan[]) {
  try { ls()?.setItem(PREFIXO_RESULTADOS + fazendaChave(), JSON.stringify(r)); } catch { /* cheio */ }
}
/** Atualiza um resultado (ex.: conflito decidido) e avisa as telas. */
export function atualizarResultado(chave: string, patch: Partial<ResultadoSan>) {
  gravarResultados(lerResultados().map((r) => (r.chave === chave ? { ...r, ...patch } : r)));
  emitir();
}
export function ultimoEnvioOk(): string | null {
  return ls()?.getItem(PREFIXO_ULTIMO_OK + fazendaChave()) || null;
}

// ── enfileirar ──
export type NovoRegistroSan = { registro: RegistroCampo; numero: string; caixa: string; dia_nome: string | null };

/** Guarda os registros no aparelho (sempre) e tenta enviar logo em seguida.
 *  Devolve as chaves de idempotência (= id do item na fila). */
export async function enfileirarRegistros(novos: NovoRegistroSan[]): Promise<string[]> {
  const chaves: string[] = [];
  const agora = Date.now();
  for (const [i, n] of novos.entries()) {
    const chave = n.registro.chave_idempotencia || novaChave("app");
    const corpo: CorpoSan = { v: 1, registro: { ...n.registro, chave_idempotencia: chave }, numero: n.numero, caixa: n.caixa,
      dia_nome: n.dia_nome, estado: "fila" };
    await inserirNaFila({
      // +i ms: mantém a ordem FIFO mesmo para registros criados no mesmo instante.
      id: chave, criadoEm: new Date(agora + i).toISOString(), descricao: `Vacina/exame: ${n.caixa} · ${n.numero}`,
      caminho: CAMINHO_SYNC, metodo: "POST", tipo: "sanitario", status: "pendente", corpo,
    });
    chaves.push(chave);
  }
  marcarCampoAtivo();
  emitir();
  agendarEnvio();
  return chaves;
}

/** Tira da fila (desfazer antes de enviar / descartar). */
export async function descartarDaFila(chaves: string[]) {
  await removerDaFila(chaves);
  emitir();
}

/** Decisão da pessoa num item que o servidor devolveu "pendente". */
export async function decidirPendencia(item: ItemFilaSan, d: Parameters<typeof decidirItem>[1]) {
  const corpo = decidirItem(item.corpo, d);
  await atualizarNaFila(item.id, { corpo, status: "pendente", erro: undefined, tentativas: 0, proximaTentativaEm: undefined });
  emitir();
  agendarEnvio(200);
}
/** Item com erro: devolve para a fila como está (ex.: depois de cadastrar o animal). */
export async function reenviarItem(item: ItemFilaSan) {
  await atualizarNaFila(item.id, { corpo: { ...item.corpo, estado: "fila", motivo: null }, status: "pendente", erro: undefined,
    tentativas: 0, proximaTentativaEm: undefined });
  emitir();
  agendarEnvio(200);
}

// ── envio ──
// Uma chamada ao servidor por vez (lote ou heartbeat): o primeiro contato de
// um aparelho cria o registro dele no servidor, e duas chamadas simultâneas
// nesse primeiro contato colidiam na chave única (aparelho × usuário × fazenda).
let fila: Promise<unknown> = Promise.resolve();
function emSerie<T>(fn: () => Promise<T>): Promise<T> {
  const p = fila.then(fn, fn);
  fila = p.catch(() => undefined);
  return p;
}

let agendado: ReturnType<typeof setTimeout> | null = null;
/** Envia em lote daqui a pouco (junta vários "APLICADO · PRÓXIMO" seguidos). */
export function agendarEnvio(ms = 900) {
  if (typeof window === "undefined") return;
  if (agendado) clearTimeout(agendado);
  agendado = setTimeout(() => { agendado = null; sincronizarSanitario().catch(() => {}); }, ms);
}

function proximaTentativa(tentativas: number): string {
  return new Date(Date.now() + Math.min(BACKOFF_BASE_MS * Math.pow(2, tentativas), BACKOFF_TETO_MS)).toISOString();
}

export type ItemFilaSan = {
  id: string; criadoEm: string; corpo: CorpoSan; status: "pendente" | "erro"; erro?: string; tentativas?: number;
  proximaTentativaEm?: string; debugUltimoErro?: string;
};

async function itensDaFazenda(): Promise<ItemFilaSan[]> {
  const fid = getFazendaAtual()?.id ?? null;
  return (await itensDaFila("sanitario"))
    .filter((i) => i.fazendaId === undefined || i.fazendaId === fid)
    .filter((i) => i.corpo && (i.corpo as CorpoSan).v === 1) as unknown as ItemFilaSan[];
}

export type RodadaSan = { enviados: number; restantes: number; semRede: boolean; resultados: ResultadoSan[] };
let rodando: Promise<RodadaSan> | null = null;

/** Uma rodada de envio: lotes de até 100 registros "na fila", até esvaziar ou
 *  cair a rede. Sem login/fazenda não faz nada. Sempre termina com heartbeat. */
export function sincronizarSanitario(forcar = false): Promise<RodadaSan> {
  if (rodando) return rodando;
  rodando = (async (): Promise<RodadaSan> => {
    const total: RodadaSan = { enviados: 0, restantes: 0, semRede: false, resultados: [] };
    if (!getToken() || !getFazendaAtual()) return total;
    for (let volta = 0; volta < 20; volta++) {
      const agora = Date.now();
      const itens = await itensDaFazenda();
      const elegiveis = itens.filter((i) => i.corpo.estado === "fila"
        && (forcar || !i.proximaTentativaEm || Date.parse(i.proximaTentativaEm) <= agora));
      total.restantes = itens.length;
      if (!elegiveis.length) break;
      const r = await enviarLote(elegiveis.slice(0, LOTE_MAX), itens.length);
      total.enviados += r.enviados;
      total.resultados.push(...r.resultados);
      if (r.semRede) { total.semRede = true; break; }
      if (!r.progrediu) break;
    }
    total.restantes = (await itensDaFazenda()).length;
    await heartbeatSanitario().catch(() => {});
    emitir();
    return total;
  })().finally(() => { rodando = null; });
  return rodando;
}

async function enviarLote(lote: ItemFilaSan[], naFila: number): Promise<{ enviados: number; semRede: boolean; progrediu: boolean; resultados: ResultadoSan[] }> {
  const uid = dispositivoUid();
  const corpo = corpoSincronizar(uid, nomeDispositivo(), lote.map((i) => i.corpo.registro), Math.max(0, naFila - lote.length));
  let res;
  try {
    // Chave nova por TENTATIVA: o middleware de idempotência guarda a resposta
    // por chave, e o lote muda entre tentativas. A idempotência de verdade é
    // por registro (chave_idempotencia), conferida pelo back.
    res = await emSerie(() => postarCru(CAMINHO_SYNC, corpo, novaChave("lote")));
  } catch (e) {
    const motivo = e instanceof Error ? `${e.name}: ${e.message}` : String(e);
    for (const i of lote) {
      const t = (i.tentativas || 0) + 1;
      await atualizarNaFila(i.id, { tentativas: t, proximaTentativaEm: proximaTentativa(t), debugUltimoErro: motivo }, false);
    }
    return { enviados: 0, semRede: true, progrediu: false, resultados: [] };
  }
  if (!res.ok) {
    const detalhe = (await res.json().catch(() => ({}))) as { detail?: unknown };
    const msg = mensagemErroApi(detalhe?.detail) || `Erro ${res.status}`;
    if (res.status === 401 || res.status === 403 || res.status >= 500 || res.status === 409) {
      const motivo = res.status === 401 || res.status === 403 ? "Sessão expirada: entre de novo para enviar." : msg;
      for (const i of lote) {
        const t = (i.tentativas || 0) + 1;
        await atualizarNaFila(i.id, { tentativas: t, proximaTentativaEm: proximaTentativa(t), debugUltimoErro: motivo }, false);
      }
      return { enviados: 0, semRede: false, progrediu: false, resultados: [] };
    }
    // 4xx de validação do lote inteiro (um registro malformado): isola um a um.
    if (lote.length > 1) {
      let enviados = 0;
      const resultados: ResultadoSan[] = [];
      for (const i of lote) {
        const r = await enviarLote([i], naFila);
        enviados += r.enviados;
        resultados.push(...r.resultados);
        if (r.semRede) return { enviados, semRede: true, progrediu: true, resultados };
      }
      return { enviados, semRede: false, progrediu: true, resultados };
    }
    const i = lote[0];
    await atualizarNaFila(i.id, { status: "erro", erro: msg, corpo: { ...i.corpo, estado: "erro", motivo: msg } });
    const r: ResultadoSan = { chave: i.id, status: "erro", numero: i.corpo.numero, caixa: i.corpo.caixa,
      dia_id: i.corpo.registro.dia_id ?? null, registro_id: null, conflito_log_id: null, texto: msg, em: new Date().toISOString() };
    gravarResultados(juntarResultados(lerResultados(), [r]));
    return { enviados: 0, semRede: false, progrediu: true, resultados: [r] };
  }
  const saida = (await res.json()) as SincronizarOut;
  const agoraIso = new Date().toISOString();
  const { acoes, resultados } = interpretarSync(lote.map((i) => ({ id: i.id, corpo: i.corpo })), saida, agoraIso);
  const remover: string[] = [];
  for (const a of acoes) {
    if (a.tipo === "remover") remover.push(a.id);
    // "requer" também fica como status "erro" na fila genérica: a tela de
    // Sincronização mostra o motivo em vez de "aguardando envio".
    else await atualizarNaFila(a.id, { corpo: a.corpo, status: "erro",
      erro: a.erro ?? (a.corpo.motivo ? `${a.corpo.motivo} Decida em Menu › Vacinação.` : undefined),
      tentativas: 0, proximaTentativaEm: undefined }, false);
  }
  if (remover.length) await removerDaFila(remover);
  gravarResultados(juntarResultados(lerResultados(), resultados));
  try { ls()?.setItem(PREFIXO_ULTIMO_OK + fazendaChave(), agoraIso); } catch { /* ignore */ }
  return { enviados: remover.length, semRede: false, progrediu: true, resultados };
}

/** Conta ao servidor quantos registros este aparelho guarda. */
let heartbeatEmCurso: Promise<boolean> | null = null;
export function heartbeatSanitario(): Promise<boolean> {
  if (!heartbeatEmCurso) heartbeatEmCurso = emSerie(heartbeatAgora).finally(() => { heartbeatEmCurso = null; });
  return heartbeatEmCurso;
}
async function heartbeatAgora(): Promise<boolean> {
  if (!getToken() || !getFazendaAtual()) return false;
  const itens = await itensDaFazenda();
  if (!itens.length && !campoAtivo()) return false;
  const corpo = corpoHeartbeat(dispositivoUid(), nomeDispositivo(), itens.length, maisAntigoDe(itens));
  try {
    const res = await postarCru(CAMINHO_HEARTBEAT, corpo, novaChave("hb"));
    return res.ok;
  } catch {
    return false;
  }
}

let iniciado = false;
/** Liga a fila do sanitário: entra na rodada automática de sincronização do
 *  app (abertura, volta do sinal, a cada 20 s) e manda heartbeat a cada 5 min.
 *  Chamado uma vez pela casca do app (app/app/layout.tsx). */
export function iniciarCampoSanitario(): () => void {
  if (typeof window === "undefined") return () => {};
  registrarSincronizador("sanitario", async () => { await sincronizarSanitario(); });
  if (iniciado) return () => {};
  iniciado = true;
  const id = setInterval(() => { heartbeatSanitario().catch(() => {}); }, HEARTBEAT_MS);
  heartbeatSanitario().catch(() => {});
  return () => { clearInterval(id); iniciado = false; };
}

// ── leitura para as telas ──
export type EstadoFilaSan = {
  itens: ItemFilaSan[]; naFila: number; requer: ItemFilaSan[]; erros: ItemFilaSan[]; maisAntigoEm: string | null;
  atrasada: boolean; horas: number; resultados: ResultadoSan[]; carregado: boolean;
};

/** Fila do sanitário ao vivo (atualiza quando a fila ou os resultados mudam). */
export function useFilaSanitario(): EstadoFilaSan & { recarregar: () => void } {
  const [st, setSt] = useState<EstadoFilaSan>({ itens: [], naFila: 0, requer: [], erros: [], maisAntigoEm: null, atrasada: false,
    horas: 24, resultados: [], carregado: false });
  const ler = useCallback(() => {
    itensDaFazenda().then((itens) => {
      const horas = avisoOfflineHoras();
      const maisAntigoEm = maisAntigoDe(itens);
      setSt({
        itens, naFila: itens.filter((i) => i.corpo.estado === "fila").length,
        requer: itens.filter((i) => i.corpo.estado === "requer"), erros: itens.filter((i) => i.corpo.estado === "erro"),
        maisAntigoEm, atrasada: filaAtrasada(maisAntigoEm, Date.now(), horas), horas, resultados: lerResultados(), carregado: true,
      });
    }).catch(() => setSt((s) => ({ ...s, carregado: true })));
  }, []);
  useEffect(() => {
    ler();
    window.addEventListener(EVENTO_OUTBOX, ler);
    window.addEventListener(EVENTO_SAN, ler);
    const t = setInterval(ler, 60000); // o aviso de 24 h aparece sozinho, sem sinal
    return () => { window.removeEventListener(EVENTO_OUTBOX, ler); window.removeEventListener(EVENTO_SAN, ler); clearInterval(t); };
  }, [ler]);
  return { ...st, recarregar: ler };
}
