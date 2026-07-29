"use client";
import { useCallback, useEffect, useState } from "react";
import { fetchEstadosReprodutivos, type EstadoReprodutivoAnimal } from "@/lib/api";

// Rótulo de cada estado ao vivo (mesmas chaves do backend,
// ver fazenda/rules/estado_reprodutivo.py).
export const ROTULO_ESTADO: Record<string, string> = {
  gestante: "Gestante", inseminada: "Inseminada", em_protocolo: "Em protocolo (IA atual)",
  pev: "PEV", apta: "Apta", atrasada: "Atrasada", nao_apta: "Não apta", vazia: "Vazia",
};

type Mapa = Map<string, EstadoReprodutivoAnimal>;

// O hook é usado por vários componentes da mesma tela (picker, modal, tabela).
// Sem este cache de módulo cada instância dispararia a própria requisição.
// O TTL curto existe porque lançar serviço/parto/diagnóstico muda o estado:
// dedupa a tela inteira, mas não segura dado velho pela sessão toda.
const TTL_MS = 30_000;
let cache: Mapa | null = null;
let cacheEm = 0;
let emVoo: Promise<Mapa> | null = null;

function carregar(): Promise<Mapa> {
  if (cache && performance.now() - cacheEm < TTL_MS) return Promise.resolve(cache);
  if (!emVoo) {
    emVoo = fetchEstadosReprodutivos()
      .then((r) => {
        cache = new Map(r.animais.map((a) => [a.numero, a]));
        cacheEm = performance.now();
        return cache;
      })
      .catch(() => new Map<string, EstadoReprodutivoAnimal>()) // silencioso: cai no "—"
      .finally(() => { emVoo = null; });
  }
  return emVoo;
}

/** Descarta o cache — chamar depois de lançar serviço/parto/diagnóstico, que
 *  são justamente os eventos que mudam o estado reprodutivo. */
export function invalidarEstadosReprodutivos() {
  cache = null;
}

/** Estado reprodutivo AO VIVO por número de animal — substitui a leitura do
 *  texto congelado de Animal.sit_rep nas telas de exibição/seleção. */
export function useEstadosReprodutivos() {
  const [porNumero, setPorNumero] = useState<Mapa>(() => cache || new Map());
  useEffect(() => {
    let vivo = true;
    carregar().then((m) => { if (vivo) setPorNumero(m); });
    return () => { vivo = false; };
  }, []);
  // Estável enquanto o mapa não muda: as telas usam isto dentro de useMemo.
  const rotuloDe = useCallback((numero: string): string => {
    const e = porNumero.get(numero);
    return e ? (ROTULO_ESTADO[e.estado] || e.estado) : "—";
  }, [porNumero]);
  return { porNumero, rotuloDe };
}
