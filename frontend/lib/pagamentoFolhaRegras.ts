// Regras do PAGAMENTO da folha com valor distinto por verba — o pop-up que o
// dono pediu: "no ato do pagamento, deve ser possível clicar no vale ou outra
// verba, lançar valor distinto e a diferença, em pop up, decidir se é
// desconto, desconsiderar, re-parcelar".
//
// Sem nenhum import de runtime (só tipos, que o compilador apaga), no molde de
// lib/holeriteRegras.ts: é o que permite testar com o runner nativo do Node.
// Ver lib/pagamentoFolhaRegras.test.ts.
//
// O QUE MORA AQUI, e por quê: quem pode ser editado (a coluna de edição, com
// "Editar" e o cadeado), o que a tela recusa antes de mandar (salário para
// menor, verba contratual sem confirmação, diferença de vale sem decisão) e o
// que viaja no POST. Todas são as MESMAS réguas que o servidor aplica —
// `rh_folha_pagar.py` e `rules/verba_pagamento.py` recusam de novo, porque
// nenhuma dessas travas pode existir só no navegador —, e o único jeito de a
// tela não discordar da recusa que ela mesma vai receber é a régua ser
// explícita e testada dos dois lados. A tela (PagarFolhaModal.tsx) fica só com
// o que é pintura.
import type { LinhaHolerite } from "./api";

/** Meio centavo: abaixo disso, dois valores em reais são o mesmo valor. */
const CENTAVO = 0.005;

export type DecisaoDiferenca = "abater" | "desconsiderar" | "reparcelar" | "acrescimo_avulso";

/**
 * Os dois estados da COLUNA DE EDIÇÃO que o dono pediu, mais o caso especial
 * do salário.
 *
 * "livre"      → a tela escreve **Editar**. O valor da verba é MEDIDO no mês
 *                (quanto de vale foi descontado, quanto se bonificou, quantos
 *                dias de vale-transporte): não existe valor prometido a
 *                alterar, e editar aqui é dizer o que aconteceu.
 * "contratual" → a tela desenha o **cadeado**. O valor é determinado pela lei
 *                ou pelo contrato (INSS, IR, aumento incorporado, indenização,
 *                reembolso, desconto amarrado a uma compra). O cadeado NÃO
 *                bloqueia: clicado, avisa que a alteração vale daquele momento
 *                em diante e, confirmada, libera o campo.
 * "salario"    → cadeado igual, e depois da confirmação as regras próprias:
 *                para maior vira o novo salário; para menor é recusado.
 *
 * POR QUE ISTO NÃO É UM `natureza === "salarial"`. O dono nomeou a bonificação
 * entre as verbas de "Editar", e bonificação TEM natureza salarial (CLT,
 * art. 457, §1º). O eixo que ele enxerga não é o regime tributário — é se o
 * valor é medido no mês ou prometido no contrato. A distinção não existia no
 * modelo e ganhou um campo próprio no catálogo do servidor (`alteracao`, em
 * `rules/rubrica_folha.py`), de onde ela chega até aqui dentro da origem da
 * linha. A tela NÃO tem uma segunda lista de códigos: quem classifica rubrica
 * é o servidor, que é quem recusa a gravação.
 */
export type ClasseEdicao = "livre" | "contratual" | "salario";

/** O que o servidor recebe para alterar cada verba (ver `PagarFolhaDados`). */
export type AlvoEdicao =
  | { tipo: "vale"; parcelaId: number; valeId: number }
  | { tipo: "rubrica"; rubricaId: number }
  | { tipo: "inss" }
  | { tipo: "ir" }
  | { tipo: "salario" }
  | { tipo: "outros" };

/** Uma linha do holerite como a coluna de edição a enxerga. */
export type VerbaDaFolha = {
  /** Identidade estável da linha na tela (chave de React e do mapa de
   *  valores digitados). Nunca o índice da lista: reordenar o discriminado
   *  faria o valor digitado numa verba pular para outra. */
  chave: string;
  alvo: AlvoEdicao;
  classe: ClasseEdicao;
  descricao: string;
  referencia: string;
  previsto: number;
  /** Desconto (sai do líquido) × vencimento (entra). Só para a tela dizer o
   *  que o valor faz — nenhuma regra deste módulo depende disso. */
  ehDesconto: boolean;
};

/**
 * A classe de cada linha FIXA do discriminado — as que não são rubrica de
 * catálogo. Espelha `CLASSE_POR_TIPO_DE_LINHA` de
 * `backend/fazenda/rules/verba_pagamento.py`, e é o único lugar onde a tela
 * classifica sozinha: são tipos estruturais do holerite, não códigos de um
 * catálogo que muda.
 *
 * `liquido` fica de fora porque é o TOTAL do recibo, não uma verba — editá-lo
 * seria editar a soma das outras. `ferias`, `terco`, `abono` e qualquer tipo
 * futuro também ficam de fora: o padrão de quem este módulo não conhece é não
 * deixar editar.
 */
const CLASSE_POR_TIPO: Record<string, ClasseEdicao> = {
  bruto: "salario",
  inss: "contratual",
  ir: "contratual",
  vale: "livre",
  outros: "livre",
};

/**
 * As mensagens literais do salário para MENOR, exatamente como o dono as
 * ditou — e exatamente como o servidor as devolve no 400
 * (`verba_pagamento.MENSAGEM_SALARIO_MENOR` / `NOTA_SALARIO_MENOR`).
 *
 * O fundamento da recusa dura, sem "confirmar mesmo assim": CLT, art. 468 —
 * alteração contratual lesiva ao empregado é NULA. Por isso o pop-up tem só
 * o botão Fechar, e por isso a nota diz onde a redução PODE ser feita, quando
 * ela é legítima (acordo coletivo, art. 7º, VI, da Constituição).
 */
export const MENSAGEM_SALARIO_MENOR =
  "O valor informado é inferior ao salário do funcionário. Não é permitida a alteração contratual lesiva.";
export const NOTA_SALARIO_MENOR =
  "a alteração do salário do funcionário para o valor informado deverá ser feita diretamente em " +
  "Administração > Configurações > Cadastro > Pessoas > Editar cadastro do funcionário > Salário-base (R$).";

/**
 * Uma parcela de VALE — a única verba cuja diferença abre uma DECISÃO.
 *
 * Todas as verbas passaram a ser editáveis (ver `VerbaDaFolha`), mas só o vale
 * representa dívida da pessoa, e só sobre uma dívida "deixa de ser cobrado",
 * "a fazenda assume", "volta para o saldo" e "é cobrança própria deste mês"
 * significam alguma coisa. Nas demais, o valor novo é simplesmente o valor
 * novo: quem grava é `alteracoesDoPagamento`, sem decisão nenhuma a tomar.
 */
export type VerbaPagavel = {
  parcelaId: number;
  valeId: number;
  descricao: string;
  referencia: string;
  previsto: number;
};

/**
 * O discriminado virado lista de verbas com a coluna de edição resolvida —
 * o que a tabela do pop-up desenha, linha a linha.
 *
 * Linha que este módulo não sabe classificar sai de fora (devolve `null`) em
 * vez de virar uma verba de classe inventada: sem classe não há botão, e sem
 * botão ninguém edita. É o padrão seguro para o dia em que um tipo novo de
 * linha aparecer no holerite.
 */
export function verbaDaLinha(linha: LinhaHolerite): VerbaDaFolha | null {
  const origem = linha.origem;
  const previsto = arredonda2(linha.desconto ?? linha.provento ?? Math.abs(linha.valor));
  const descricao = linha.descricao || linha.label;
  const ehDesconto = linha.desconto != null;
  const comum = { descricao, referencia: linha.referencia, previsto, ehDesconto };

  if (linha.tipo === "vale") {
    // O tipo da linha e a origem são conferidos os dois: `tipo === "vale"` diz
    // o que a linha É, e a origem é o que carrega o id da parcela — sem ele
    // não há o que mandar ao servidor, e a verba não pode ser editável. O
    // discriminante é escrito à mão em vez de chamar `ehOrigemVale` de
    // holeriteRegras: estes módulos de regra não importam nada em tempo de
    // execução, é o que os deixa rodar no runner nativo do Node (`npm test`).
    // `parcela_id` é anulável no contrato da origem (holerite de folha
    // congelada antes de a origem existir): sem ele a verba fica só de leitura
    // em vez de virar um campo que não salva.
    if (!origem || origem.tipo !== "vale" || origem.parcela_id == null) return null;
    return {
      ...comum, classe: "livre",
      chave: `vale:${origem.parcela_id}`,
      alvo: { tipo: "vale", parcelaId: origem.parcela_id, valeId: origem.vale_id },
    };
  }

  if (linha.tipo === "vencimento_extra" || linha.tipo === "desconto_extra") {
    if (!origem || origem.tipo !== "rubrica") return null;
    return {
      ...comum,
      // A classe da rubrica vem do SERVIDOR (`origem.alteracao`, alimentada
      // pelo catálogo em rules/rubrica_folha.py). Rubrica antiga — de uma
      // discriminação congelada antes deste campo existir — cai em
      // "contratual": pedir confirmação é o lado seguro de não saber.
      classe: origem.alteracao === "livre" ? "livre" : "contratual",
      chave: `rubrica:${origem.rubrica_id}`,
      alvo: { tipo: "rubrica", rubricaId: origem.rubrica_id },
    };
  }

  const classe = CLASSE_POR_TIPO[linha.tipo];
  if (!classe) return null;
  if (linha.tipo === "bruto") return { ...comum, classe, chave: "salario", alvo: { tipo: "salario" } };
  if (linha.tipo === "outros") return { ...comum, classe, chave: "outros", alvo: { tipo: "outros" } };
  return { ...comum, classe, chave: linha.tipo, alvo: { tipo: linha.tipo as "inss" | "ir" } };
}

export function verbasDaFolha(detalhe: LinhaHolerite[]): VerbaDaFolha[] {
  const verbas: VerbaDaFolha[] = [];
  for (const linha of detalhe) {
    const verba = verbaDaLinha(linha);
    if (verba) verbas.push(verba);
  }
  return verbas;
}

/**
 * As parcelas de VALE — as únicas cuja diferença abre as decisões (abater,
 * desconsiderar, reparcelar, acréscimo avulso). Derivada de `verbasDaFolha`
 * para não haver duas leituras do mesmo discriminado.
 */
export function verbasPagaveis(detalhe: LinhaHolerite[]): VerbaPagavel[] {
  const verbas: VerbaPagavel[] = [];
  for (const v of verbasDaFolha(detalhe)) {
    if (v.alvo.tipo !== "vale") continue;
    verbas.push({
      parcelaId: v.alvo.parcelaId,
      valeId: v.alvo.valeId,
      descricao: v.descricao,
      referencia: v.referencia,
      previsto: v.previsto,
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
 * Descontando a MAIS, DUAS e só estas duas — é o que o dono pediu, e a razão
 * de nenhuma das outras caber é a mesma de sempre: não existe valor deixado de
 * cobrar para abater nem para a fazenda assumir, porque o dinheiro foi
 * descontado de verdade. O que sobra é escolher o que o excedente É:
 *   reparcelar        → antecipação do vale; o saldo cai e o prazo é refeito;
 *   acrescimo_avulso  → cobrança própria deste mês; o vale fica intacto e a
 *                       diferença vira uma linha avulsa do holerite (a mesma
 *                       rubrica avulsa de sempre — não há um segundo conceito
 *                       de acréscimo no sistema).
 */
export function decisoesDisponiveis(diferenca: number): DecisaoDiferenca[] {
  if (!temDiferenca(diferenca)) return [];
  if (diferenca < 0) return ["reparcelar", "acrescimo_avulso"];
  return ["abater", "desconsiderar", "reparcelar"];
}

/** O líquido que sai do caixa depois da edição: menos vale descontado, mais
 *  dinheiro para a pessoa — na mesma medida da diferença. */
export function liquidoComDiferenca(liquidoPrevisto: number, diferenca: number): number {
  return arredonda2(liquidoPrevisto + diferenca);
}

/**
 * O líquido depois de TODAS as verbas alteradas, e não só do vale.
 *
 * A conta é uma só para as seis: alterar um DESCONTO (vale, INSS, IR, outros,
 * desconto avulso) move o líquido no sentido contrário; alterar um VENCIMENTO
 * (salário, bonificação, vale-transporte) move no mesmo sentido. É a mesma
 * regra que `liquidoComDiferenca` já aplicava ao vale — generalizada em vez de
 * repetida, para não existirem duas contas de líquido na mesma tela.
 */
export function liquidoComAlteracoes(
  liquidoPrevisto: number, verbas: VerbaDaFolha[], valores: Record<string, number>,
): number {
  let liquido = liquidoPrevisto;
  for (const verba of verbas) {
    if (!verbaAlterada(verba, valores)) continue;
    const delta = arredonda2(valores[verba.chave] - verba.previsto);
    liquido += verba.ehDesconto ? -delta : delta;
  }
  return arredonda2(liquido);
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
    return "Esta decisão não cabe para uma verba descontada a mais — o que resta decidir é se o excedente antecipa o saldo do vale ou é cobrança própria deste mês.";
  }
  if (decisao === "reparcelar" && !(opcoes.parcelas && opcoes.parcelas >= 1)) {
    return "Informe em quantas parcelas a diferença será dividida.";
  }
  return null;
}

// ---------------------------------------------------------------------------
// A coluna de edição: o que a tela recusa antes de mandar, e o que ela manda
// ---------------------------------------------------------------------------

/** "igual" | "maior" | "menor" — qual dos pop-ups do salário abre. */
export function direcaoDoSalario(previsto: number, informado: number): "igual" | "maior" | "menor" {
  if (Math.abs(arredonda2(previsto) - arredonda2(informado)) <= CENTAVO) return "igual";
  return informado > previsto ? "maior" : "menor";
}

/** A verba mudou de valor? (meio centavo de tolerância, como todo o resto). */
export function verbaAlterada(verba: VerbaDaFolha, valores: Record<string, number>): boolean {
  const valor = valores[verba.chave];
  if (valor === undefined) return false;
  return Math.abs(arredonda2(verba.previsto) - arredonda2(valor)) > CENTAVO;
}

/**
 * O que impede confirmar o pagamento por causa das ALTERAÇÕES de verba —
 * null quando não há impedimento.
 *
 * Duas recusas, as duas espelhadas no servidor (`_conferir_salario` e
 * `_exigir_confirmacao` em rh_folha_pagar.py):
 *
 * 1. salário para MENOR. É a recusa dura do art. 468 da CLT, e ela não tem
 *    "confirmar mesmo assim": a alteração contratual lesiva ao empregado é
 *    nula, então não existe consentimento que a valide. A tela devolve a
 *    MESMA frase que o 400 do servidor devolveria.
 * 2. verba contratual alterada sem o cadeado confirmado. Recusar aqui é o que
 *    impede o usuário descobrir, depois de digitar tudo, que o pagamento não
 *    passa — e depois de a folha estar paga não há correção possível, porque
 *    a discriminação é congelada.
 */
export function erroDasAlteracoes(
  verbas: VerbaDaFolha[], valores: Record<string, number>, confirmadas: Set<string>,
): string | null {
  for (const verba of verbas) {
    if (!verbaAlterada(verba, valores)) continue;
    const valor = valores[verba.chave];
    if (verba.classe === "salario" && direcaoDoSalario(verba.previsto, valor) === "menor") {
      return MENSAGEM_SALARIO_MENOR;
    }
    if (verba.classe !== "livre" && !confirmadas.has(verba.chave)) {
      return `Confirme o aviso do cadeado em “${verba.descricao}” antes de pagar: a alteração vale daquele momento em diante.`;
    }
  }
  return null;
}

/**
 * As alterações no formato que o servidor recebe (ver `PagarFolhaDados`).
 *
 * Só viaja o que MUDOU: mandar todas as verbas com o valor atual faria o
 * servidor conferir confirmação de cadeado em linha que ninguém tocou.
 */
export function alteracoesDoPagamento(
  verbas: VerbaDaFolha[], valores: Record<string, number>, confirmadas: Set<string>,
): {
  rubricas: { rubrica_id: number; valor_pago: number; confirmado: boolean }[];
  retencoes: { tipo: "inss" | "ir"; valor_pago: number; confirmado: boolean }[];
  salario?: { valor_pago: number; confirmado: boolean };
  outros_descontos?: { valor_pago: number };
} {
  const rubricas: { rubrica_id: number; valor_pago: number; confirmado: boolean }[] = [];
  const retencoes: { tipo: "inss" | "ir"; valor_pago: number; confirmado: boolean }[] = [];
  let salario: { valor_pago: number; confirmado: boolean } | undefined;
  let outros: { valor_pago: number } | undefined;

  for (const verba of verbas) {
    if (!verbaAlterada(verba, valores)) continue;
    const valor_pago = arredonda2(valores[verba.chave]);
    const confirmado = confirmadas.has(verba.chave);
    if (verba.alvo.tipo === "rubrica") rubricas.push({ rubrica_id: verba.alvo.rubricaId, valor_pago, confirmado });
    else if (verba.alvo.tipo === "inss" || verba.alvo.tipo === "ir") {
      retencoes.push({ tipo: verba.alvo.tipo, valor_pago, confirmado });
    } else if (verba.alvo.tipo === "salario") salario = { valor_pago, confirmado };
    else if (verba.alvo.tipo === "outros") outros = { valor_pago };
  }
  return { rubricas, retencoes, salario, outros_descontos: outros };
}
