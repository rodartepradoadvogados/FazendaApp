"use client";
// ─────────────────────────────────────────────────────────────────────────────
// Infraestrutura offline do app móvel (/app):
//
// 1. useOnline()        — está com internet agora? (bolinha verde/vermelha)
// 2. fetchComCache()    — GET com cache local: online atualiza o cache; sem
//                         internet devolve a última versão vista.
// 3. enviarOuEnfileirar() — POST que, sem internet, entra numa FILA local
//                         (outbox) e é enviado sozinho quando a conexão volta.
// 4. sincronizar()      — percorre a fila e envia; roda no evento 'online',
//                         na abertura do app e periodicamente como garantia.
//
// Tudo em localStorage — simples, robusto e suficiente para o volume de
// lançamentos de uma fazenda (não é um banco local completo).
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
// ─────────────────────────────────────────────────────────────────────────────
import { useEffect, useState } from "react";
import { API, getToken } from "@/lib/api";

const CHAVE_OUTBOX = "mob_outbox";
const PREFIXO_CACHE = "mob_cache_";
export const EVENTO_OUTBOX = "mob-outbox-mudou";

// Timeout de rede — rede rural ruim não pode travar a tela pendurada.
const TIMEOUT_ENVIO_MS = 12000;
// Backoff por item: 30s, 60s, 120s, 240s, teto de 5min. Evita martelar um
// servidor fora do ar ou um token que não vai se renovar sozinho.
const BACKOFF_BASE_MS = 30000;
const BACKOFF_TETO_MS = 5 * 60000;

export type ItemOutbox = {
  id: string;
  criadoEm: string;         // ISO
  descricao: string;        // texto humano: "Inseminação — vaca 150"
  caminho: string;          // ex.: "/reproducao/inseminacao"
  metodo: "POST" | "PUT" | "DELETE";
  corpo: unknown;
  erro?: string;            // só 4xx de validação (dado inválido) — nunca 401/403/5xx/timeout
  tentativas?: number;      // quantas vezes já tentou (rede/401/403/5xx) — base do backoff
  proximaTentativaEm?: string; // ISO — sincronizar() pula o item até esse instante
};

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

// ── Fila de envio (outbox) ───────────────────────────────────────────────────
export function pendentes(): ItemOutbox[] {
  try { return JSON.parse(localStorage.getItem(CHAVE_OUTBOX) || "[]"); } catch { return []; }
}

function gravar(fila: ItemOutbox[]) {
  localStorage.setItem(CHAVE_OUTBOX, JSON.stringify(fila));
  window.dispatchEvent(new CustomEvent(EVENTO_OUTBOX));
}

export function descartarPendente(id: string) {
  gravar(pendentes().filter((i) => i.id !== id));
}

function enfileirar(item: Omit<ItemOutbox, "id" | "criadoEm">) {
  const novo: ItemOutbox = { ...item, id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`, criadoEm: new Date().toISOString() };
  gravar([...pendentes(), novo]);
  return novo;
}

// fetch cru com timeout — sem Authorization automático de mais, sem logout
// automático em 401. Usado só pelo caminho de sincronização em background;
// o envio interativo (enviarOuEnfileirar, com o app em primeiro plano)
// continua usando authFetch de propósito — se o token caiu ali, faz sentido
// mandar pro login na hora, é uma ação que o usuário está vendo acontecer.
async function fetchCru(caminho: string, metodo: string, corpo: unknown): Promise<Response> {
  const token = getToken();
  const controlador = new AbortController();
  const timeoutId = setTimeout(() => controlador.abort(), TIMEOUT_ENVIO_MS);
  try {
    return await fetch(`${API}${caminho}`, {
      method: metodo,
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify(corpo),
      cache: "no-store",
      signal: controlador.signal,
    });
  } finally {
    clearTimeout(timeoutId);
  }
}

function proximaTentativa(tentativas: number): string {
  const espera = Math.min(BACKOFF_BASE_MS * Math.pow(2, tentativas), BACKOFF_TETO_MS);
  return new Date(Date.now() + espera).toISOString();
}

/**
 * Tenta enviar agora; sem internet (ou falha de rede), guarda na fila para
 * sincronizar depois. Erro do servidor (4xx/5xx) com internet É repassado —
 * significa dado inválido, e o usuário deve corrigir na hora.
 * Retorna { enviado } para a tela dizer "salvo" ou "guardado para enviar".
 */
export async function enviarOuEnfileirar(caminho: string, corpo: unknown, descricao: string, metodo: "POST" | "PUT" | "DELETE" = "POST"): Promise<{ enviado: boolean }> {
  if (!navigator.onLine) {
    enfileirar({ caminho, metodo, corpo, descricao });
    return { enviado: false };
  }
  const { authFetch } = await import("@/lib/api");
  try {
    const res = await authFetch(`${API}${caminho}`, {
      method: metodo,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corpo),
      signal: AbortSignal.timeout(TIMEOUT_ENVIO_MS),
    });
    if (!res.ok) {
      const detalhe = await res.json().catch(() => ({}));
      throw new Error(detalhe.detail || `Erro ${res.status} ao salvar`);
    }
    return { enviado: true };
  } catch (e) {
    // TypeError = falha de REDE (não chegou ao servidor); timeout também
    // aborta como erro de rede, não de validação → nos dois casos, enfileira.
    if (e instanceof TypeError || (e instanceof DOMException && e.name === "AbortError")) {
      enfileirar({ caminho, metodo, corpo, descricao });
      return { enviado: false };
    }
    throw e; // resposta do servidor (validação etc.) → o formulário mostra
  }
}

// ── Sincronização ────────────────────────────────────────────────────────────
let sincronizando = false;

/** Envia a fila em ordem. Falha de rede/401/403/5xx = "tenta depois" (nunca
 *  grava erro nem desloga) — só 4xx de validação de dado vira `erro` visível
 *  em Menu > Pendentes, exigindo decisão do usuário. */
export async function sincronizar(): Promise<{ enviados: number; restantes: number }> {
  if (sincronizando || !navigator.onLine) return { enviados: 0, restantes: pendentes().length };
  sincronizando = true;
  let enviados = 0;
  try {
    const agora = Date.now();
    for (const item of pendentes()) {
      if (item.erro) continue; // recusado antes (dado inválido) — espera decisão do usuário
      if (item.proximaTentativaEm && new Date(item.proximaTentativaEm).getTime() > agora) continue; // backoff ainda em curso
      try {
        const res = await fetchCru(item.caminho, item.metodo, item.corpo);
        if (res.ok) {
          descartarPendente(item.id);
          enviados++;
          continue;
        }
        if (res.status === 401 || res.status === 403 || res.status >= 500) {
          // Sessão expirada ou servidor fora do ar — tenta de novo mais
          // tarde, nunca descarta nem marca como erro definitivo.
          const tentativas = (item.tentativas || 0) + 1;
          gravar(pendentes().map((i) => (i.id === item.id ? { ...i, tentativas, proximaTentativaEm: proximaTentativa(tentativas) } : i)));
          continue;
        }
        // 4xx "de verdade" (400/404/409/422...) = dado inválido, exige o usuário.
        const detalhe = await res.json().catch(() => ({}));
        gravar(pendentes().map((i) => (i.id === item.id ? { ...i, erro: detalhe.detail || `Erro ${res.status}` } : i)));
      } catch {
        // Rede caiu de novo (ou timeout) no meio da fila — para por aqui,
        // tenta o resto na próxima rodada de sincronizar().
        break;
      }
    }
  } finally {
    sincronizando = false;
  }
  return { enviados, restantes: pendentes().length };
}

/** Hook: quantidade (e lista) de pendentes, atualizada ao vivo. */
export function usePendentes(): ItemOutbox[] {
  const [fila, setFila] = useState<ItemOutbox[]>([]);
  useEffect(() => {
    const ler = () => setFila(pendentes());
    ler();
    window.addEventListener(EVENTO_OUTBOX, ler);
    window.addEventListener("storage", ler);
    return () => { window.removeEventListener(EVENTO_OUTBOX, ler); window.removeEventListener("storage", ler); };
  }, []);
  return fila;
}

/** Liga a sincronização automática: ao voltar a internet, ao abrir e
 *  periodicamente como garantia (o backoff de cada item, acima, evita
 *  martelar o servidor — este intervalo só precisa ser curto o bastante
 *  pra sentir a volta da conexão). */
export function iniciarSincronizacaoAutomatica(): () => void {
  const aoConectar = () => { sincronizar(); };
  window.addEventListener("online", aoConectar);
  sincronizar();
  const id = setInterval(() => {
    const agora = Date.now();
    if (pendentes().some((i) => !i.erro && (!i.proximaTentativaEm || new Date(i.proximaTentativaEm).getTime() <= agora))) sincronizar();
  }, 20000);
  return () => { window.removeEventListener("online", aoConectar); clearInterval(id); };
}
