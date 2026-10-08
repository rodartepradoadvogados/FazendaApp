/**
 * Natureza econômica do lançamento (Fase A dos Relatórios do Financeiro).
 * Espelho de backend/fazenda/rules/natureza.py — ver docs/financeiro-regras-v2.md.
 *
 * Não confundir com `PlanoContaGerencial.natureza` (serviço × produto): esta diz
 * se o dinheiro é custo/receita da atividade (Operacional) ou outra coisa —
 * compra de bem, empréstimo, aporte... Só muda os relatórios na fazenda que
 * ligou "usar as regras novas" em Parâmetros financeiros.
 */
export type NaturezaFin =
  | "OPERACIONAL" | "INVESTIMENTO" | "FINANCIAMENTO" | "CAPITAL"
  | "TRANSFERENCIA" | "ADIANTAMENTO" | "OBRIGACAO";

export const NATUREZAS_FIN: { valor: NaturezaFin; rotulo: string; ajuda: string }[] = [
  { valor: "OPERACIONAL", rotulo: "Operacional", ajuda: "Custo ou receita da atividade: entra na DRE e nos custos." },
  { valor: "INVESTIMENTO", rotulo: "Investimento (bem do imobilizado)", ajuda: "Compra de máquina, benfeitoria, matriz ou reprodutor: fica fora da DRE e entra só pela depreciação." },
  { valor: "FINANCIAMENTO", rotulo: "Financiamento", ajuda: "Entrada de empréstimo ou pagamento do principal: fora da DRE (o juro é despesa, em Outras)." },
  { valor: "CAPITAL", rotulo: "Capital do sócio", ajuda: "Aporte ou retirada de sócio: fora da DRE." },
  { valor: "TRANSFERENCIA", rotulo: "Transferência entre contas", ajuda: "Só move dinheiro entre contas da fazenda." },
  { valor: "ADIANTAMENTO", rotulo: "Adiantamento (vale)", ajuda: "Valor a receber de alguém: fora da DRE." },
  { valor: "OBRIGACAO", rotulo: "Obrigação já reconhecida", ajuda: "Quita algo que já entrou como custo antes (ex.: guia de retidos)." },
];

const ROTULOS: Record<string, string> = {
  ...Object.fromEntries(NATUREZAS_FIN.map((n) => [n.valor, n.rotulo])),
  NAO_INFORMADA: "Fora da DRE, motivo não informado",
  MISTA: "Mista (cada item tem a sua)",
};

export function rotuloNatureza(valor: string | null | undefined): string {
  if (!valor) return "Automática";
  return ROTULOS[valor] ?? valor;
}
