// Árvore dos Relatórios do Financeiro organizada por PERGUNTA (Fase B — PLANO.md
// §4): Resultado, Caixa, Leite, Plano, Registros. Cada grupo é uma aba; cada
// relatório, uma sub-aba. Nenhum relatório antigo some: os ids continuam os
// mesmos (links salvos, ?sub= e ?ir= seguem valendo) e os que mudaram de lugar
// são redirecionados. PURO — testes em relatoriosNavegacao.test.ts.

export type ItemRelatorio = { id: string; label: string };
export type GrupoRelatorio = { id: string; label: string; pergunta: string; itens: ItemRelatorio[] };

export const GRUPOS_RELATORIOS: GrupoRelatorio[] = [
  { id: "rg-resultado", label: "Resultado", pergunta: "Estou ganhando?", itens: [
    { id: "rel_litro", label: "Resultado por litro" },
    { id: "rel_dre", label: "DRE da fazenda" },
    { id: "dre_contas", label: "DRE por conta (tela anterior)" },
  ] },
  { id: "rg-caixa", label: "Caixa", pergunta: "Quando o caixa aperta?", itens: [
    { id: "rel_caixa", label: "Caixa real" },
    { id: "rel_fluxo", label: "Fluxo de caixa" },
    { id: "rel_livro", label: "Livro caixa da atividade rural" },
  ] },
  { id: "rg-leite", label: "Leite", pergunta: "Quanto custa meu litro?", itens: [
    { id: "custos", label: "Custos do leite" },
    { id: "rmca", label: "Sobra da comida (RMCA)" },
  ] },
  { id: "rg-plano", label: "Plano", pergunta: "Gastei o que planejei?", itens: [
    { id: "rel_orcamento", label: "Orçamento" },
    { id: "rel_cenarios", label: "Cenários" },
    // Telas anteriores (paridade): item a item com observação e Importar para Pedidos.
    { id: "orcamento_itens", label: "Orçamento item a item (tela anterior)" },
    { id: "planejamento_financeiro", label: "Cenários por conta (tela anterior)" },
  ] },
  { id: "rg-registros", label: "Registros", pergunta: "De onde vem cada número?", itens: [
    { id: "compra_venda_animais", label: "Compra e venda de animais" },
    { id: "compra_semen", label: "Compra de sêmen" },
  ] },
];

/** Relatórios novos, feitos no molde único (os outros continuam na tela de antes até a Fase C). */
export const RELATORIOS_NO_MOLDE = new Set(["rel_litro", "rel_dre", "rel_caixa", "rel_fluxo", "rel_livro", "rel_orcamento", "rel_cenarios"]);

/** Ids antigos que mudaram de lugar → onde estão agora. */
export const REDIRECIONAMENTOS: Record<string, string> = {
  dre: "rel_dre",
  // Fase C1 (Caixa): as telas antigas deram lugar às do molde.
  caixa_real: "rel_caixa",
  fluxo: "rel_fluxo",
  // Fase C3: o orçamento no molde (a tela anterior continua em "orcamento_itens").
  orcamento: "rel_orcamento",
};

export function idDoRelatorio(id: string): string {
  return REDIRECIONAMENTOS[id] ?? id;
}

export function grupoDe(id: string): GrupoRelatorio | null {
  const alvo = idDoRelatorio(id);
  return GRUPOS_RELATORIOS.find((g) => g.itens.some((i) => i.id === alvo)) ?? null;
}

/** Todos os ids que são relatório (para empilhar no histórico ao navegar entre eles). */
export const IDS_RELATORIOS = new Set(GRUPOS_RELATORIOS.flatMap((g) => g.itens.map((i) => i.id)));
