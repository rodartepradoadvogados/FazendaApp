"use client";
// Peças compartilhadas pelas sub-telas do Menu (todas SÓ LEITURA):
//  - useCarregar: leitura com cache offline (fetchComCache) + estados prontos.
//  - AvisoCopia: aviso discreto "Cópia de <data>" quando os dados vieram do cache.
//  - Carregando / Vazio: estados simpáticos.
//  - Bolinha/corSemaforo: semáforo (vermelho/amarelo/verde/branco) dos relatórios.
import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { fetchComCache, cacheEm } from "@/lib/offline";

export function fmtCacheEm(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

/** Leitura com cache: online atualiza; offline devolve a última cópia salva. */
export function useCarregar<T>(chave: string, buscar: () => Promise<T>) {
  const [dados, setDados] = useState<T | null>(null);
  const [doCache, setDoCache] = useState(false);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState(false);

  const carregar = useCallback(async () => {
    setCarregando(true);
    const r = await fetchComCache<T>(chave, buscar);
    setDados(r.dados);
    setDoCache(r.doCache);
    // fetchComCache engole o erro e cai no cache; se falhou ONLINE é erro real
    // (servidor fora / 403), não "offline".
    setErro(r.doCache && typeof navigator !== "undefined" && navigator.onLine);
    setCarregando(false);
    // buscar muda a cada render; a chave identifica a leitura.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chave]);

  useEffect(() => { carregar(); }, [carregar]);
  return { dados, doCache, carregando, erro, recarregar: carregar };
}

/** Aviso discreto de que os dados exibidos são uma cópia local (offline). */
export function AvisoCopia({ chave, mostrar }: { chave: string; mostrar: boolean }) {
  const iso = mostrar ? cacheEm(chave) : null;
  if (!iso) return null;
  return (
    <p style={{ fontSize: "0.78rem", color: "var(--mob-muted)", margin: "0 0 0.9rem" }}>
      Cópia de {fmtCacheEm(iso)}
    </p>
  );
}

export function Carregando() {
  return <p style={{ color: "var(--mob-muted)", padding: "1.5rem 0" }}>Carregando…</p>;
}

export function Vazio({ children }: { children: ReactNode }) {
  return (
    <div style={{ textAlign: "center", padding: "2.5rem 1rem", color: "var(--mob-muted)" }}>
      <p style={{ fontSize: "1.05rem", fontWeight: 700, color: "var(--mob-text)" }}>{children}</p>
    </div>
  );
}

const COR_SEMAFORO: Record<string, string> = {
  vermelho: "var(--mob-vermelho)",
  amarelo: "var(--mob-ambar)",
  verde: "var(--mob-verde)",
  branco: "var(--mob-muted)",
};
export function corSemaforo(c?: string | null): string {
  return COR_SEMAFORO[(c || "").toLowerCase()] || "var(--mob-muted)";
}

/** Bolinha do semáforo. */
export function Bolinha({ cor }: { cor?: string | null }) {
  return (
    <span style={{ width: 12, height: 12, borderRadius: "50%", background: corSemaforo(cor), flexShrink: 0, display: "inline-block" }} />
  );
}

/** Número grande do animal (ou rótulo curto) usado nas listas. */
export function NumAnimal({ children }: { children: ReactNode }) {
  return <span style={{ fontWeight: 800, fontSize: "1.05rem", color: "var(--mob-text)" }}>{children}</span>;
}
