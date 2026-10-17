"use client";
// Estado compartilhado das telas de lote: passo atual (com a direção da animação) e seleção que sobrevive ao app ser
// interrompido (mesmo rascunho em localStorage que as outras telas de Lançar usam — ver useRascunho em ../comum.tsx).
import { useState } from "react";

// O app rola dentro do <body> (overflow-y: auto), não na janela: sem rolar os dois, o passo novo abriria no meio da tela.
function rolarAoTopo() {
  try {
    window.scrollTo({ top: 0 });
    document.body.scrollTo({ top: 0 });
  } catch { /* sem window (teste/SSR) — segue */ }
}

/** Passo atual + sentido da transição (avançar entra pela direita, voltar pela esquerda). */
export function usePassos<T extends number | string>(inicial: T) {
  const [passo, setPasso] = useState<T>(inicial);
  const [volta, setVolta] = useState(false);
  function ir(novo: T, voltando = false) {
    setVolta(voltando);
    setPasso(novo);
    rolarAoTopo();
  }
  return { passo, volta, ir };
}

function lerRascunho(chave: string): string[] {
  if (typeof window === "undefined") return [];
  try {
    const bruto = window.localStorage.getItem(chave);
    const lista: unknown = bruto ? JSON.parse(bruto) : [];
    return Array.isArray(lista) ? lista.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return [];
  }
}

function gravarRascunho(chave: string, sel: ReadonlySet<string>) {
  if (typeof window === "undefined") return;
  try {
    if (sel.size) window.localStorage.setItem(chave, JSON.stringify([...sel]));
    else window.localStorage.removeItem(chave);
  } catch { /* modo privado / cota cheia: segue sem rascunho */ }
}

/**
 * Conjunto de animais marcados, guardado como rascunho. `obrigatorios` entram marcados na abertura: só para animais
 * que a PESSOA acabou de escolher em outra tela (o animal da ficha, as matrizes do diagnóstico negativo) — fora isso,
 * nada vem marcado sozinho.
 */
export function useSelecaoPersistida(chave: string, obrigatorios: readonly string[] = []) {
  const chaveCompleta = `rascunho_lancar_${chave}`;
  const [sel, setSel] = useState<Set<string>>(() => {
    const s = new Set(lerRascunho(chaveCompleta));
    for (const o of obrigatorios) if (o) s.add(o);
    return s;
  });
  function definir(novo: Set<string>) {
    setSel(novo);
    gravarRascunho(chaveCompleta, novo);
  }
  return { sel, definir, limpar: () => definir(new Set()) };
}
