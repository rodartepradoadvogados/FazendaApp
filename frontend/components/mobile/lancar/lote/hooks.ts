"use client";
// Estado compartilhado das telas de lote: passo atual (com a direção da animação e o foco no passo novo) e seleção que
// sobrevive ao app ser interrompido (mesmo rascunho em localStorage que as outras telas de Lançar usam — ver useRascunho
// em ../comum.tsx), separada por fazenda.
import { useState } from "react";
import { getFazendaAtual } from "@/lib/api";

// O app rola dentro do <body> (overflow-y: auto), não na janela: sem rolar os dois, o passo novo abriria no meio da tela.
function rolarAoTopo() {
  try {
    window.scrollTo({ top: 0 });
    document.body.scrollTo({ top: 0 });
  } catch { /* sem window (teste/SSR) — segue */ }
}

/** Vibração curta de confirmação; sem suporte (iOS) é um no-op. */
export function vibrar(padrao: number | number[]) {
  try { navigator.vibrate?.(padrao); } catch { /* sem suporte — segue sem vibrar */ }
}

/** ref de callback do contêiner de cada passo: ao montar, leva o foco para ele (o botão que a pessoa tocou sumiu).
 * Se um filho já tomou o foco (o título do resultado), não rouba. */
export function focarAoMontar(el: HTMLElement | null) {
  if (el && !el.contains(document.activeElement)) el.focus({ preventScroll: true });
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
 * Conjunto de animais marcados, guardado como rascunho POR FAZENDA (os brincos se repetem entre fazendas: a seleção — e
 * principalmente uma confirmação — de uma não pode aparecer na outra). `obrigatorios` entram marcados na abertura: só para
 * animais que a PESSOA acabou de escolher em outra tela (o animal da ficha, as matrizes do diagnóstico negativo). Quem
 * decide se uma marca ainda vale é a regra de cada tela (ver selecaoEfetiva), não este hook.
 * `definir` aceita o conjunto novo ou uma função do conjunto atual (para o laço de envio tirar um por vez sem closure velho).
 */
export function useSelecaoPersistida(chave: string, obrigatorios: readonly string[] = []) {
  const chaveCompleta = `rascunho_lancar_${chave}_f${getFazendaAtual()?.id ?? 0}`;
  const [sel, setSel] = useState<Set<string>>(() => {
    const s = new Set(lerRascunho(chaveCompleta));
    for (const o of obrigatorios) if (o) s.add(o);
    return s;
  });
  function definir(novo: Set<string> | ((atual: Set<string>) => Set<string>)) {
    setSel((atual) => {
      const proximo = typeof novo === "function" ? novo(atual) : novo;
      gravarRascunho(chaveCompleta, proximo);
      return proximo;
    });
  }
  return { sel, definir };
}
