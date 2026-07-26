import { useRef } from "react";

// Sistema de abas estilo navegador (ver TabsShell) — até 5 abas simultâneas,
// cada uma um iframe independente (preserva estado/rolagem exatamente onde
// estava ao trocar). abrirNovaAba() funciona de qualquer janela, mesmo de
// dentro de uma aba que já é um iframe: sempre manda a mensagem para
// window.top (a janela de cima trata a abertura), nunca tenta abrir por
// conta própria — evita duas barras de abas aninhadas.
export const MENSAGEM_ABRIR_ABA = "fazenda:abrir-aba";
// Cada aba (nativa ou iframe) reporta pro topo qual é a PÁGINA atual (não a
// sub-aba) sempre que muda — é assim que a guia mostra "Reprodução" em vez
// de ficar presa em "Principal"/no nome de quando foi aberta. Só quem está
// DENTRO de uma aba precisa mandar isso (ver notificarTituloAtual); a aba
// nativa lê o próprio pathname direto, sem mensagem.
export const MENSAGEM_TITULO_ATUALIZADO = "fazenda:titulo-atualizado";

// Profundidade da sub-navegação de onde a aba foi aberta — 0 (ou undefined)
// = link direto da Sidebar (guia com contorno dourado, como já era). 1 = veio
// de uma sub-aba (2º nível); 2 = de uma sub-sub-aba (3º nível). Só afeta a
// cor de fundo da guia na faixa (ver TabsShell) — nunca o conteúdo.
export type ProfundidadeAba = 0 | 1 | 2;

export function abrirNovaAba(url: string, titulo: string, profundidade?: ProfundidadeAba): void {
  if (typeof window === "undefined") return;
  window.top?.postMessage({ tipo: MENSAGEM_ABRIR_ABA, url, titulo, profundidade }, window.location.origin);
}

export function notificarTituloAtual(titulo: string): void {
  if (typeof window === "undefined" || !estaDentroDeAba()) return;
  window.top?.postMessage({ tipo: MENSAGEM_TITULO_ATUALIZADO, titulo }, window.location.origin);
}

export function estaDentroDeAba(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.self !== window.top;
  } catch {
    // Acesso a window.top bloqueado (cross-origin) — nunca deveria acontecer
    // aqui (mesma origem sempre), mas por segurança trata como "dentro de aba"
    // para nunca desenhar uma barra de abas aninhada por engano.
    return true;
  }
}

const LIMIAR_DUPLO_CLIQUE_MS = 280;

/** Discrimina 1 clique de 2 num mesmo elemento (ex.: link da Sidebar) sem
 * depender de onDoubleClick puro — um <a>/<Link> dispara onClick a cada
 * clique individual, então precisamos segurar o 1º clique por um instante
 * pra saber se um 2º vai chegar antes de navegar. Uso: onClick={handler}. */
export function useCliqueOuDuploClique(aoClicar: () => void, aoDarDuploClique: () => void) {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  return () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
      aoDarDuploClique();
      return;
    }
    timerRef.current = setTimeout(() => {
      timerRef.current = null;
      aoClicar();
    }, LIMIAR_DUPLO_CLIQUE_MS);
  };
}
