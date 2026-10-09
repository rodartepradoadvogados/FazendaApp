// Janelas do site (Modal e gaveta): larguras e pilha de overlays.
// Funções puras, sem DOM — o que depende do navegador fica em components/useOverlay.ts.

/** Teto do "dobro" de uma janela: acima disso o formulário só ganha espaço em branco. */
export const TETO_DOBRO_PX = 1120;

/** Largura-padrão da gaveta de lançamento (Lançamentos › … › abrir lançamento). */
export const LARGURA_GAVETA_PADRAO = "min(80vw, 1320px)";

/**
 * Largura da gaveta "Dar baixa" (Contas a pagar / a receber): o DOBRO dos 560 px
 * que o painel lateral antigo tinha. Em celular vira a tela inteira.
 */
export const LARGURA_GAVETA_BAIXA = "min(1120px, 100vw)";

/** Texto padrão de "fechar com formulário sujo" (mesmo de Lançamentos). */
export const MSG_SAIR_SEM_SALVAR = "Você tem certeza que quer sair dessa página? Os dados não salvos serão perdidos.";

/** Dobro da largura (px), limitado ao teto. */
export function dobroEmPx(px: number, teto: number = TETO_DOBRO_PX): number {
  if (!Number.isFinite(px) || px <= 0) return teto;
  return Math.min(Math.round(px * 2), teto);
}

/**
 * Largura CSS de um Modal cuja largura ANTIGA era `px`: o dobro (com teto) e
 * nunca mais que 95% da tela — em celular a janela ocupa a largura toda sem
 * rolagem horizontal. Uso: `<Modal width={larguraDobrada(520)} …>`.
 */
export function larguraDobrada(px: number): string {
  return `min(${dobroEmPx(px)}px, 95vw)`;
}

// ── Pilha de overlays (Esc só age no do topo) ─────────────────────────────

export type EntradaPilha = { id: number; fecharComEsc: boolean };

/** Põe a entrada no topo; se o id já existe, só atualiza a flag e mantém a posição. */
export function empilhar(pilha: readonly EntradaPilha[], entrada: EntradaPilha): EntradaPilha[] {
  if (pilha.some((e) => e.id === entrada.id)) return pilha.map((e) => (e.id === entrada.id ? entrada : e));
  return [...pilha, entrada];
}

export function desempilhar(pilha: readonly EntradaPilha[], id: number): EntradaPilha[] {
  return pilha.filter((e) => e.id !== id);
}

export function ehTopo(pilha: readonly EntradaPilha[], id: number): boolean {
  return pilha.length > 0 && pilha[pilha.length - 1].id === id;
}

/**
 * Esc fecha SÓ o overlay do topo, e só se ele permitir. Se o topo é uma janela
 * travada (`fecharComEsc: false`), Esc não faz nada — também não "vaza" para o
 * overlay de baixo. Devolve o id a fechar, ou null.
 */
export function idParaFecharComEsc(pilha: readonly EntradaPilha[]): number | null {
  if (!pilha.length) return null;
  const topo = pilha[pilha.length - 1];
  return topo.fecharComEsc ? topo.id : null;
}
