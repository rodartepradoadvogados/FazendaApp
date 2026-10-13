// Árvore dos Relatórios do Financeiro organizada por PERGUNTA (Fase B — PLANO.md
// §4): Painel (entrada, Fase C), Resultado, Caixa, Leite, Plano, Registros. Cada grupo é uma aba; cada
// relatório, uma sub-aba. Nenhum relatório antigo some: os ids continuam os
// mesmos (links salvos, ?sub= e ?ir= seguem valendo) e os que mudaram de lugar
// são redirecionados. PURO — testes em relatoriosNavegacao.test.ts.

export type ItemRelatorio = { id: string; label: string };
export type GrupoRelatorio = { id: string; label: string; pergunta: string; itens: ItemRelatorio[] };

export const GRUPOS_RELATORIOS: GrupoRelatorio[] = [
  // Fase C: a entrada dos Relatórios — as 4 perguntas do dono em uma olhada.
  { id: "rg-painel", label: "Painel", pergunta: "Como está a fazenda?", itens: [
    { id: "painel_dono", label: "Painel do dono" },
  ] },
  { id: "rg-resultado", label: "Resultado", pergunta: "Estou ganhando?", itens: [
    { id: "rel_litro", label: "Resultado por litro" },
    { id: "rel_dre", label: "DRE da fazenda" },
    // O que a DRE deixa de fora por falta de classificação, lançamento a lançamento (T2).
    { id: "classificar", label: "Classificar" },
  ] },
  { id: "rg-caixa", label: "Caixa", pergunta: "Quando o caixa aperta?", itens: [
    { id: "rel_caixa", label: "Caixa real" },
    { id: "rel_fluxo", label: "Fluxo de caixa" },
    { id: "rel_livro", label: "Livro caixa da atividade rural" },
  ] },
  { id: "rg-leite", label: "Leite", pergunta: "Quanto custa meu litro?", itens: [
    { id: "custos", label: "Custos do leite" },
    { id: "rmca", label: "Sobra da comida (RMCA)" },
    { id: "reguas_referencia", label: "Réguas de referência" },
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
  // Fase C5: entrega ao contador (pacote, fechamento do mês e conciliação bancária).
  { id: "rg-contador", label: "Entrega ao contador", pergunta: "Está pronto para o contador?", itens: [
    { id: "pacote_contador", label: "Pacote do contador" },
    { id: "fechamento_mes", label: "Fechamento do mês" },
    { id: "conciliacao", label: "Conciliação bancária" },
  ] },
];

/** Relatórios novos, feitos no molde único (os outros continuam na tela de antes até a Fase C). */
export const RELATORIOS_NO_MOLDE = new Set([
  "painel_dono", // Fase C4 (Painel)
  "rel_litro", "rel_dre", "classificar", // Fase B (Resultado) + T2 (Classificar)
  "rel_caixa", "rel_fluxo", "rel_livro", // Fase C1 (Caixa)
  "custos", "rmca", // Fase C2 (Leite)
  "reguas_referencia", // Fase C4 (Leite)
  "rel_orcamento", "rel_cenarios", // Fase C3 (Plano)
  "compra_venda_animais", "compra_semen", // Fase C2 (Registros)
  "pacote_contador", "fechamento_mes", "conciliacao", // Fase C5 (Entrega ao contador)
]);

/** Ids antigos que mudaram de lugar → onde estão agora. */
export const REDIRECIONAMENTOS: Record<string, string> = {
  dre: "rel_dre",
  // T2: a DRE por conta (tela anterior) saiu; a classificação das contas é a tela Classificar.
  dre_contas: "classificar",
  // Fase C1 (Caixa): as telas antigas deram lugar às do molde.
  caixa_real: "rel_caixa",
  fluxo: "rel_fluxo",
  // T7: o nome curto do grupo (links escritos à mão, ?ir=caixa) abre o primeiro relatório dele, o Caixa real.
  caixa: "rel_caixa",
  // Fase C2: as quatro telas de custo viraram as visões de "Custos do leite" (?visao=).
  custo_litro_leite: "custos", custo_vaca_lote: "custos", custo_hectare: "custos", custo_safra: "custos",
  // Fase C3: o orçamento no molde (a tela anterior continua em "orcamento_itens").
  orcamento: "rel_orcamento",
  // Fase C4: nomes curtos do mockup (links escritos à mão) → os ids da árvore.
  painel: "painel_dono",
  reguas: "reguas_referencia",
};

/** Id antigo de custo → a visão de "Custos do leite" que ele abre (?visao=). */
export const VISAO_DO_ID_ANTIGO: Record<string, string> = {
  custo_litro_leite: "litro", custo_vaca_lote: "lote", custo_hectare: "ha", custo_safra: "safra",
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

// ── Visibilidade por contrato (Plano Financeiro §2.7) ──────────────────────────────────────────
// Fazenda só-financeiro ([financeiro, pedidos]) não tem rebanho, planejamento nem agricultura:
// relatório cuja FONTE não existe não aparece no menu (nunca devolve 403) e, se aberto por link
// salvo, mostra "fonte não contratada" — jamais R$ 0, que seria informação contábil falsa.
// As chaves são módulos COMERCIAIS do contrato; `tem` é o moduloContratado de lib/modulos.ts.

export type TemModulo = (chave: string) => boolean;

/** Módulos (todos, E) de que cada relatório depende além do Financeiro. Ausente = só financeiro. */
const MODULOS_DO_RELATORIO: Record<string, string[]> = {
  // Registros: animais e sêmen vivem no Rebanho.
  compra_venda_animais: ["rebanho"],
  compra_semen: ["rebanho"],
  // Plano: orçamento e cenários são do módulo Planejamento (main.py: /planejamento).
  rel_orcamento: ["planejamento"],
  rel_cenarios: ["planejamento"],
  orcamento_itens: ["planejamento"],
  planejamento_financeiro: ["planejamento"],
};

/** Visões de "Custos do leite" (?visao=) que precisam de fonte além do Financeiro (litro é sempre possível). */
const MODULOS_DA_VISAO_CUSTOS: Record<string, string[]> = {
  lote: ["rebanho"], // custo por vaca/lote: lotes e animais
  ha: ["agricultura"], // custo por hectare: áreas
  safra: ["agricultura"], // custo por safra: safras
};

const ROTULO_MODULO: Record<string, string> = {
  rebanho: "Rebanho", planejamento: "Planejamento", agricultura: "Agricultura", estoque: "Estoque",
};

/** Ids de relatório acolhem os antigos (redirecionados) — a checagem vale para o destino. */
export function modulosFaltandoDoRelatorio(id: string, tem: TemModulo): string[] {
  return (MODULOS_DO_RELATORIO[idDoRelatorio(id)] ?? []).filter((m) => !tem(m));
}

export function relatorioDisponivel(id: string, tem: TemModulo): boolean {
  return modulosFaltandoDoRelatorio(id, tem).length === 0;
}

/** A árvore sem o que a fazenda não pode abrir; grupo que fica sem item some. */
export function relatoriosVisiveis(tem: TemModulo): GrupoRelatorio[] {
  return GRUPOS_RELATORIOS
    .map((g) => ({ ...g, itens: g.itens.filter((i) => relatorioDisponivel(i.id, tem)) }))
    .filter((g) => g.itens.length > 0);
}

/** Visões de Custos do leite (ids de ?visao=) abertas para a fazenda. */
export function visoesCustosDisponiveis(tem: TemModulo): string[] {
  return ["litro", "lote", "ha", "safra"].filter((v) => (MODULOS_DA_VISAO_CUSTOS[v] ?? []).every(tem));
}

/** Texto de "fonte não contratada" para um relatório (ou null se pode abrir). */
export function avisoFonteNaoContratada(id: string, tem: TemModulo): string | null {
  const falta = modulosFaltandoDoRelatorio(id, tem);
  if (!falta.length) return null;
  const nomes = falta.map((m) => ROTULO_MODULO[m] ?? m).join(" e ");
  return `Fonte não contratada: este relatório usa dados do módulo ${nomes}, que não faz parte do contrato desta fazenda. Fale com a CowData para incluir.`;
}

/** Primeiro relatório aberto da árvore visível (destino quando o atual some). */
export function primeiroRelatorioVisivel(tem: TemModulo): string {
  return relatoriosVisiveis(tem)[0]?.itens[0]?.id ?? "painel_dono";
}
