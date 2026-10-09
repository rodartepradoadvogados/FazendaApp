import type { DreResposta } from "@/lib/api";

/**
 * Fase A, PR 8 — DRE única (uma fonte de verdade para o resultado).
 *
 * Com as regras novas ligadas na fazenda (`financeiro_regras_v2`), os KPIs e o
 * gráfico da aba DRE leem o `resumo` que o SERVIDOR tira da cascata (receita
 * líquida, despesas, resultado, margem): investimento, aporte, principal,
 * adiantamento e não classificado ficam fora, a depreciação entra — o mesmo
 * número da cascata, do e-mail do Portal e da Capa. Sem o resumo (regras
 * antigas, ou API ainda na versão anterior durante um deploy), a tela segue
 * com a soma dos lançamentos no cliente, como antes.
 */
export type KpisDre = {
  receita: number;
  despesa: number;
  resultado: number;
  /** null quando não há receita para calcular a margem. */
  margemPct: number | null;
  fonte: "servidor" | "cliente";
  /** O que NÃO entrou no resultado (só com o resumo do servidor). */
  foraDaDre: number | null;
  naoClassificado: number | null;
};

export function kpisDre(
  dados: Pick<DreResposta, "resumo"> | null | undefined,
  somaCliente: { receitas: number; despesas: number },
): KpisDre {
  const r = dados?.resumo;
  if (r) {
    return {
      receita: r.receita_liquida,
      despesa: r.despesas,
      resultado: r.resultado_liquido,
      margemPct: r.margem_liquida_pct,
      fonte: "servidor",
      foraDaDre: r.fora_da_dre_total,
      naoClassificado: r.nao_classificado,
    };
  }
  const resultado = somaCliente.receitas - somaCliente.despesas;
  return {
    receita: somaCliente.receitas,
    despesa: somaCliente.despesas,
    resultado,
    margemPct: somaCliente.receitas > 0 ? Math.round((1000 * resultado) / somaCliente.receitas) / 10 : null,
    fonte: "cliente",
    foraDaDre: null,
    naoClassificado: null,
  };
}

export type RegimeDre = "competencia" | "caixa";

/** Regime vindo da URL (`?regime=caixa`); qualquer outra coisa é competência. */
export function regimeDaUrl(busca: string): RegimeDre {
  return new URLSearchParams(busca).get("regime") === "caixa" ? "caixa" : "competencia";
}

/**
 * Orçado × realizado (PR 8): cor e rótulo do desvio pela SITUAÇÃO que o
 * servidor calcula — desvio colorido só quando há orçado; "sem orçamento" e
 * o que está fora do resultado ficam neutros; receita acima do orçado é
 * favorável e despesa acima, desfavorável.
 */
export type SituacaoOrcamento =
  | "favoravel" | "desfavoravel" | "no_orcado" | "sem_orcamento" | "coberta_pelo_grupo" | "fora_do_resultado";

export function apresentacaoSituacao(situacao: SituacaoOrcamento | string | null | undefined): { cor: string; rotulo: string } {
  switch (situacao) {
    case "favoravel": return { cor: "var(--green-light)", rotulo: "Favorável" };
    case "desfavoravel": return { cor: "var(--red)", rotulo: "Desfavorável" };
    case "no_orcado": return { cor: "var(--text)", rotulo: "No orçado" };
    case "coberta_pelo_grupo": return { cor: "var(--text-muted)", rotulo: "No orçamento do grupo" };
    case "fora_do_resultado": return { cor: "var(--text-muted)", rotulo: "Fora do resultado" };
    default: return { cor: "var(--text-muted)", rotulo: "Sem orçamento" };
  }
}
