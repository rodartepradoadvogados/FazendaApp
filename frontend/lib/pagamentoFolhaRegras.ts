// Regras do PAGAMENTO da folha com valor distinto por verba — o pop-up que o
// dono pediu: "no ato do pagamento, deve ser possível clicar no vale ou outra
// verba, lançar valor distinto e a diferença, em pop up, decidir se é
// desconto, desconsiderar, re-parcelar".
//
// Sem nenhum import de runtime (só tipos, que o compilador apaga), no molde de
// lib/holeriteRegras.ts: é o que permite testar com o runner nativo do Node.
// Ver lib/pagamentoFolhaRegras.test.ts.
//
// O QUE MORA AQUI, e por quê: a decisão de quando o pop-up EXIGE escolha. Ela
// é a mesma regra que o servidor aplica (`rh_folha_pagar.py` recusa diferença
// sem decisão), e o único jeito de a tela não discordar da recusa que ela
// mesma vai receber é a régua ser explícita e testada dos dois lados. A tela
// (PagarFolhaModal.tsx) fica só com o que é pintura.
import type { LinhaHolerite } from "./api";

/** Meio centavo: abaixo disso, dois valores em reais são o mesmo valor. */
const CENTAVO = 0.005;

export type DecisaoDiferenca = "abater" | "desconsiderar" | "reparcelar";

/**
 * Uma verba do holerite que pode receber valor distinto no ato do pagamento.
 *
 * Hoje só parcela de VALE entra: é a única verba que representa dívida da
 * pessoa, e as três decisões ("deixa de ser cobrado", "a fazenda assume",
 * "volta para o saldo") são as três coisas que se pode fazer com uma dívida
 * não cobrada. Salário, INSS, IR e rubricas não são dívida de ninguém —
 * mudá-los é corrigir o lançamento, o que se faz em "Editar lançamento",
 * antes de pagar.
 */
export type VerbaPagavel = {
  parcelaId: number;
  valeId: number;
  descricao: string;
  referencia: string;
  previsto: number;
};

export function verbasPagaveis(detalhe: LinhaHolerite[]): VerbaPagavel[] {
  const verbas: VerbaPagavel[] = [];
  for (const linha of detalhe) {
    // O tipo da linha e a origem são conferidos os dois: `tipo === "vale"` diz
    // o que a linha É, e a origem é o que carrega o id da parcela — sem ele
    // não há o que mandar ao servidor, e a verba não pode ser editável. O
    // discriminante é escrito à mão em vez de chamar `ehOrigemVale` de
    // holeriteRegras: estes módulos de regra não importam nada em tempo de
    // execução, é o que os deixa rodar no runner nativo do Node (`npm test`).
    const origem = linha.origem;
    if (linha.tipo !== "vale" || !origem || origem.tipo !== "vale") continue;
    // `parcela_id` é anulável no contrato da origem (holerite de folha
    // congelada antes de a origem existir): sem ele não há o que mandar ao
    // servidor, então a verba fica só de leitura em vez de virar um campo que
    // não salva.
    if (origem.parcela_id == null) continue;
    verbas.push({
      parcelaId: origem.parcela_id,
      valeId: origem.vale_id,
      descricao: linha.descricao || linha.label,
      referencia: linha.referencia,
      previsto: arredonda2(linha.desconto ?? Math.abs(linha.valor)),
    });
  }
  return verbas;
}

export function arredonda2(n: number): number {
  return Math.round(n * 100) / 100;
}

/**
 * Diferença do pagamento: previsto − pago, somando as verbas editáveis.
 *
 * POSITIVA = descontou-se MENOS vale do que a parcela previa (sobra dívida
 * sem destino, e o líquido pago à pessoa sobe na mesma medida).
 * NEGATIVA = descontou-se MAIS (o excedente antecipa o saldo do vale).
 */
export function diferencaPagamento(
  verbas: VerbaPagavel[], valores: Record<number, number>,
): number {
  let diferenca = 0;
  for (const v of verbas) {
    const pago = valores[v.parcelaId];
    diferenca += v.previsto - (pago === undefined ? v.previsto : pago);
  }
  return arredonda2(diferenca);
}

export function temDiferenca(diferenca: number): boolean {
  return Math.abs(diferenca) > CENTAVO;
}

/**
 * Quais decisões cabem para esta diferença.
 *
 * Descontando a MAIS, só reparcelar: não existe valor deixado de cobrar para
 * abater nem para a fazenda assumir — o dinheiro foi descontado de verdade, e
 * o que resta decidir é como fica o saldo restante do vale.
 */
export function decisoesDisponiveis(diferenca: number): DecisaoDiferenca[] {
  if (!temDiferenca(diferenca)) return [];
  if (diferenca < 0) return ["reparcelar"];
  return ["abater", "desconsiderar", "reparcelar"];
}

/** O líquido que sai do caixa depois da edição: menos vale descontado, mais
 *  dinheiro para a pessoa — na mesma medida da diferença. */
export function liquidoComDiferenca(liquidoPrevisto: number, diferenca: number): number {
  return arredonda2(liquidoPrevisto + diferenca);
}

/**
 * O que impede confirmar o pagamento — null quando pode confirmar.
 *
 * A primeira regra é o pedido literal do dono: com diferença e sem decisão
 * escolhida, o pagamento é recusado. Recusar na tela (em vez de deixar o
 * servidor recusar) é o que permite dizer isso ANTES de a folha virar recibo:
 * depois de paga, a discriminação é congelada e nada nela se corrige.
 */
export function erroDoPagamento(
  diferenca: number,
  decisao: DecisaoDiferenca | null,
  opcoes: { parcelas?: number; dataPagamento?: string } = {},
): string | null {
  if (!opcoes.dataPagamento) return "Informe a data do pagamento.";
  if (!temDiferenca(diferenca)) return null;
  if (!decisao) {
    return "Há diferença entre o previsto e o pago. Escolha o que fazer com ela antes de confirmar.";
  }
  if (!decisoesDisponiveis(diferenca).includes(decisao)) {
    return "Esta decisão não cabe para uma verba descontada a mais — o que resta decidir é como fica o saldo do vale.";
  }
  if (decisao === "reparcelar" && !(opcoes.parcelas && opcoes.parcelas >= 1)) {
    return "Informe em quantas parcelas a diferença será dividida.";
  }
  return null;
}
