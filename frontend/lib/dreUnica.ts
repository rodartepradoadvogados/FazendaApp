/**
 * Orçado × realizado (Fase A, PR 8): cor e rótulo do desvio pela SITUAÇÃO que o
 * servidor calcula — desvio colorido só quando há orçado; "sem orçamento" e
 * o que está fora do resultado ficam neutros; receita acima do orçado é
 * favorável e despesa acima, desfavorável.
 *
 * (Os KPIs da aba "DRE por conta" que viviam aqui — `kpisDre` e `regimeDaUrl` — saíram junto
 * com ela: a DRE da fazenda lê o número direto da cascata do servidor e a classificação
 * mora em Relatórios › Resultado › Classificar.)
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
