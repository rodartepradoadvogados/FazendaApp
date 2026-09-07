// Regras das duas VOLTAS ATRÁS sobre um vale — estornar o abatimento e voltar
// a descontar o mês desconsiderado (backend: `rh_vale_acoes.py`, ações
// `estornar_abatimento` e `reverter_desconsideracao`).
//
// Sem nenhum import de runtime (só tipos, que o compilador apaga), no molde de
// lib/pagamentoFolhaRegras.ts: é o que permite testar com o runner nativo do
// Node. Ver lib/desfazerValeRegras.test.ts.
//
// O QUE MORA AQUI, e por quê: a PRÉVIA do estorno — quanto volta ao saldo e
// quanto cada parcela pendente passa a valer. O caso que fez estas ações
// existirem foi um clique na ação errada (o dono quis "a fazenda assume" e
// lançou um abatimento de R$ 167,85, que rateou sozinho sobre 12 parcelas de
// R$ 985,00 e as deixou em R$ 971,01). Confirmar a volta sem ver os números
// seria repetir o mesmo erro ao contrário — por isso a tela mostra, antes do
// clique, o valor exato que cada parcela vai passar a ter.
//
// O rateio é uma CÓPIA CONSCIENTE da conta do servidor (`_reescalar_parcelas`):
// proporcional ao peso de cada parcela, última absorvendo o arredondamento. É
// o único jeito de a prévia dizer a mesma coisa que o POST vai gravar; se as
// duas divergirem, o teste do round-trip (backend) e o daqui apontam para o
// mesmo lugar.
import type { ValeAcaoContexto } from "./api";

type ParcelaContexto = ValeAcaoContexto["parcelas"][number];

/** Centavos, sempre — dinheiro nunca fica com cauda binária. */
function c2(valor: number): number {
  return Math.round(valor * 100) / 100;
}

/** As parcelas em que o servidor ainda mexe, na mesma ordem dele (competência
 *  crescente; `pendente` já vem calculado pelo GET, a tela não recalcula). */
export function parcelasPendentes(contexto: ValeAcaoContexto): ParcelaContexto[] {
  return contexto.parcelas.filter((p) => p.pendente);
}

/**
 * Redistribui `saldoNovo` entre as parcelas pendentes proporcionalmente ao
 * peso que cada uma tem hoje, com a ÚLTIMA absorvendo o arredondamento —
 * mesma conta de `_reescalar_parcelas` no servidor.
 */
export function reescalarParcelas(
  pendentes: ParcelaContexto[], saldo: number, saldoNovo: number,
): number[] {
  if (saldo <= 0) return pendentes.map(() => 0);
  const novos: number[] = [];
  let acumulado = 0;
  pendentes.forEach((p, i) => {
    const valor = i < pendentes.length - 1
      ? c2((saldoNovo * p.valor) / saldo)
      : c2(saldoNovo - acumulado);
    acumulado = c2(acumulado + valor);
    novos.push(Math.max(valor, 0));
  });
  return novos;
}

export type PreviaEstorno = {
  /** O que de fato será estornado (em branco = o abatimento inteiro). */
  valor: number;
  saldoAtual: number;
  saldoNovo: number;
  linhas: { competencia: string; de: number; para: number }[];
  /** Por que o estorno ainda não pode ser confirmado — a MESMA recusa que o
   *  servidor daria, dita antes do clique. `null` quando dá para confirmar. */
  impedimento: string | null;
};

/**
 * A prévia do estorno: quanto volta ao saldo e quanto cada parcela pendente
 * passa a valer. `valorDigitado` em branco significa "o abatimento inteiro",
 * que é o padrão da ação no servidor.
 */
export function previaEstorno(contexto: ValeAcaoContexto, valorDigitado: string): PreviaEstorno {
  const disponivel = c2(contexto.valor_abatido);
  const valor = valorDigitado.trim() === "" ? disponivel : c2(Number(valorDigitado) || 0);
  const pendentes = parcelasPendentes(contexto);
  const saldoAtual = c2(pendentes.reduce((soma, p) => soma + p.valor, 0));
  const saldoNovo = c2(saldoAtual + valor);
  const novos = reescalarParcelas(pendentes, saldoAtual, saldoNovo);

  let impedimento: string | null = null;
  if (disponivel <= 0) impedimento = "Este vale não tem abatimento a estornar.";
  else if (valor <= 0) impedimento = "Informe um valor de estorno maior que zero.";
  else if (valor > disponivel) impedimento = `Há R$ ${disponivel.toFixed(2)} disponíveis para estorno.`;
  else if (pendentes.length === 0) {
    impedimento = "Não há parcela pendente onde devolver o valor — reparcele o vale antes.";
  }

  return {
    valor,
    saldoAtual,
    saldoNovo,
    linhas: pendentes.map((p, i) => ({ competencia: p.competencia, de: p.valor, para: novos[i] })),
    impedimento,
  };
}

/** Quanto volta a ser descontado do funcionário ao reverter a desconsideração
 *  de um mês — a soma das parcelas assumidas daquela competência. */
export function valorDaReversao(contexto: ValeAcaoContexto, competencia: string): number {
  return c2(
    contexto.parcelas
      .filter((p) => p.competencia === competencia && p.assumida_pela_fazenda)
      .reduce((soma, p) => soma + p.valor, 0),
  );
}
