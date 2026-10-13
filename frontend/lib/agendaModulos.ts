// O que a Agenda mostra conforme os módulos que a fazenda contratou (Plano Financeiro, §2.6).
// Fazenda só-financeiro ([financeiro, pedidos]) não tem rebanho nem estoque: nada de
// Reprodução/Sanidade/Alertas de estoque no Painel, nada de vínculo a animal/lote no evento
// manual e nenhuma chamada fadada a 403 (GET /animais/, /estoque/). PURO — recebe o
// predicado `tem(chave)` (moduloContratado de lib/modulos.ts) para ser testável sem navegador.
// Chaves = módulos COMERCIAIS do contrato (rebanho, reprodutivo, sanitario, produtivo, financeiro, estoque…).

export type TemModulo = (chave: string) => boolean;

/** Categoria do evento da Agenda → módulo comercial que a alimenta (Atividades e Gestão/Financeiro não dependem de rebanho). */
const MODULO_DA_CATEGORIA: Record<string, string | null> = {
  "Reprodutivo": "reprodutivo",
  "Sanidade": "sanitario",
  "Produção": "produtivo",
  "Gestão/Financeiro": null,
  "Atividades": null,
};

/** Categorias (filtro e formulário de evento manual) que fazem sentido para a fazenda. */
export function categoriasAgendaVisiveis(todas: readonly string[], tem: TemModulo): string[] {
  return todas.filter((c) => {
    const mod = MODULO_DA_CATEGORIA[c];
    return mod == null || tem(mod);
  });
}

export type GruposPainel = {
  reproducao: boolean;
  sanidade: boolean;
  /** "Alertas de estoque" (só com o módulo estoque). */
  estoque: boolean;
  /** "Contas a pagar" e "A receber" (só com o módulo financeiro). */
  financeiro: boolean;
};

/** Quais grupos/cartões do Painel existem para esta fazenda. */
export function gruposPainelVisiveis(tem: TemModulo): GruposPainel {
  return {
    reproducao: tem("reprodutivo"),
    sanidade: tem("sanitario"),
    estoque: tem("estoque"),
    financeiro: tem("financeiro"),
  };
}

/** Vínculo do evento manual a animal/lote só existe com rebanho. */
export function podeVincularAnimalLote(tem: TemModulo): boolean {
  return tem("rebanho");
}

type ContaAgenda = { valor_total?: number | null; valor_pago?: number | null };

/** Quantidade e saldo (total − pago, nunca negativo) de uma lista de contas da Agenda (a pagar ou a receber). */
export function resumoContasAgenda(contas: readonly ContaAgenda[] | null | undefined): { n: number; saldo: number } {
  const lista = Array.isArray(contas) ? contas : [];
  const saldo = lista.reduce((t, c) => t + Math.max(0, (c.valor_total || 0) - (c.valor_pago || 0)), 0);
  return { n: lista.length, saldo };
}
