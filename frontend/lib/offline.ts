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
//                         na abertura do app e a cada 30s como garantia.
//
// Tudo em localStorage — simples, robusto e suficiente para o volume de
// lançamentos de uma fazenda (não é um banco local completo).
// ─────────────────────────────────────────────────────────────────────────────
import { useEffect, useState } from "react";
import { API, authFetch } from "@/lib/api";

const CHAVE_OUTBOX = "mob_outbox";
const PREFIXO_CACHE = "mob_cache_";
export const EVENTO_OUTBOX = "mob-outbox-mudou";

export type ItemOutbox = {
  id: string;
  criadoEm: string;         // ISO
  descricao: string;        // texto humano: "Inseminação — vaca 150"
  caminho: string;          // ex.: "/reproducao/inseminacao"
  metodo: "POST" | "PUT" | "DELETE";
  corpo: unknown;
  erro?: string;            // preenchido se o servidor RECUSOU (4xx) — não retenta sozinho
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
  try {
    const res = await authFetch(`${API}${caminho}`, {
      method: metodo,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corpo),
    });
    if (!res.ok) {
      const detalhe = await res.json().catch(() => ({}));
      throw new Error(detalhe.detail || `Erro ${res.status} ao salvar`);
    }
    return { enviado: true };
  } catch (e) {
    // TypeError = falha de REDE (não chegou ao servidor) → enfileira.
    if (e instanceof TypeError) {
      enfileirar({ caminho, metodo, corpo, descricao });
      return { enviado: false };
    }
    throw e; // resposta do servidor (validação etc.) → o formulário mostra
  }
}

// ── Sincronização ────────────────────────────────────────────────────────────
let sincronizando = false;

/** Envia a fila em ordem. Falha de rede para e tenta depois; recusa do
 *  servidor marca o item com erro (fica visível em Menu > Pendentes). */
export async function sincronizar(): Promise<{ enviados: number; restantes: number }> {
  if (sincronizando || !navigator.onLine) return { enviados: 0, restantes: pendentes().length };
  sincronizando = true;
  let enviados = 0;
  try {
    for (const item of pendentes()) {
      if (item.erro) continue; // recusado antes — espera decisão do usuário
      try {
        const res = await authFetch(`${API}${item.caminho}`, {
          method: item.metodo,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(item.corpo),
        });
        if (res.ok) {
          descartarPendente(item.id);
          enviados++;
        } else {
          const detalhe = await res.json().catch(() => ({}));
          gravar(pendentes().map((i) => (i.id === item.id ? { ...i, erro: detalhe.detail || `Erro ${res.status}` } : i)));
        }
      } catch {
        break; // rede caiu de novo — tenta na próxima
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

/** Liga a sincronização automática: ao voltar a internet, ao abrir e a cada 30s. */
export function iniciarSincronizacaoAutomatica(): () => void {
  const aoConectar = () => { sincronizar(); };
  window.addEventListener("online", aoConectar);
  sincronizar();
  const id = setInterval(() => { if (pendentes().some((i) => !i.erro)) sincronizar(); }, 30000);
  return () => { window.removeEventListener("online", aoConectar); clearInterval(id); };
}
