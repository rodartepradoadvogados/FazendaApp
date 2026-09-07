// Testes de frontend/lib/pagamentoFolhaRegras.ts — o pop-up de pagar com
// valor distinto nas verbas. Rodam com o runner nativo do Node: `npm test`.
//
// O que estas regras existem para impedir, e que estes testes travam:
//  - confirmar um pagamento com diferença de vale e sem decisão escolhida (é
//    o pedido literal do dono, e é o que impede congelar um recibo que cobra
//    um desconto que não houve);
//  - oferecer "abater" ou "a fazenda assume" para quem descontou a MAIS — não
//    há valor deixado de cobrar nesses casos; e oferecer, aí, EXATAMENTE as
//    duas saídas que o dono pediu (reparcelar e acréscimo avulso);
//  - deixar alterar uma verba CONTRATUAL sem a confirmação do cadeado;
//  - deixar reduzir o salário — alteração contratual lesiva ao empregado é
//    nula (CLT, art. 468), e a recusa tem de sair com a frase exata, a mesma
//    que o servidor devolve no 400.
import { test } from "node:test";
import assert from "node:assert/strict";
import type { LinhaHolerite } from "./api.ts";
import {
  alteracoesDoPagamento, decisoesDisponiveis, diferencaPagamento, direcaoDoSalario, erroDasAlteracoes,
  erroDoPagamento, liquidoComAlteracoes, liquidoComDiferenca, temDiferenca, verbaDaLinha, verbasDaFolha,
  verbasPagaveis, MENSAGEM_SALARIO_MENOR, NOTA_SALARIO_MENOR,
} from "./pagamentoFolhaRegras.ts";

function linha(over: Partial<LinhaHolerite>): LinhaHolerite {
  return {
    label: "x", valor: 0, tipo: "bruto", descricao: "x", referencia: "",
    provento: null, desconto: null, origem: null, ...over,
  } as LinhaHolerite;
}

/** Uma rubrica avulsa do holerite, com a classe de edição que o SERVIDOR
 *  mandou (`origem.alteracao`) — a tela nunca decide isso sozinha. */
function linhaRubrica(
  rubricaId: number, valor: number,
  over: { especie?: "vencimento" | "desconto"; alteracao?: "livre" | "contratual"; codigo?: string } = {},
): LinhaHolerite {
  const especie = over.especie ?? "vencimento";
  return linha({
    tipo: especie === "vencimento" ? "vencimento_extra" : "desconto_extra",
    descricao: over.codigo ?? "Bonificação por produtividade",
    referencia: "natureza salarial · entra nas bases de INSS, IRRF e FGTS",
    valor: especie === "vencimento" ? valor : -valor,
    provento: especie === "vencimento" ? valor : null,
    desconto: especie === "vencimento" ? null : valor,
    origem: {
      tipo: "rubrica", rubrica_id: rubricaId, codigo: over.codigo ?? "bonificacao_produtividade",
      rotulo: "Bonificação por produtividade", especie, descricao: null,
      natureza: "salarial", incide_inss: true, incide_irrf: true, incide_fgts: true,
      incorpora_base: false, competencia_incorporacao: null,
      alteracao: over.alteracao ?? "livre", fundamento: "CLT, art. 457, §1º", compra: null,
    } as LinhaHolerite["origem"],
  });
}

function linhaVale(parcelaId: number, valor: number): LinhaHolerite {
  return linha({
    tipo: "vale", label: `Vale (parcela 1/3)`, descricao: "Vale — mercado",
    referencia: "Parcela 1 de 3 · vale de 10/06/2026", valor: -valor, desconto: valor,
    origem: {
      tipo: "vale", vale_id: 7, parcela_id: parcelaId, parcela: 1, parcelas_total: 3,
      valor_total: 900, data_pagamento: "2026-06-10", forma_pagamento: "pix",
      observacao: "mercado", numero_documento_pagamento: null, numero_lancamento_gerado: "2026/1",
      sem_saida_de_caixa: false, origem_lancamento: null, aplicada: true,
    } as LinhaHolerite["origem"],
  });
}

const DETALHE: LinhaHolerite[] = [
  linha({ tipo: "bruto", descricao: "Salário", provento: 3000, valor: 3000 }),
  linha({ tipo: "inss", descricao: "INSS", desconto: 270, valor: -270 }),
  linhaVale(41, 300),
  linha({ tipo: "liquido", descricao: "Líquido", valor: 2430 }),
];

test("só a parcela de vale abre as decisões de diferença — é a única verba que é dívida da pessoa", () => {
  const verbas = verbasPagaveis(DETALHE);
  assert.equal(verbas.length, 1);
  assert.deepEqual(
    { parcelaId: verbas[0].parcelaId, valeId: verbas[0].valeId, previsto: verbas[0].previsto },
    { parcelaId: 41, valeId: 7, previsto: 300 },
  );
  assert.equal(verbas[0].referencia, "Parcela 1 de 3 · vale de 10/06/2026");
});

test("linha de vale sem origem não vira verba editável — falta o id da parcela a mandar", () => {
  assert.deepEqual(verbasPagaveis([linha({ tipo: "vale", desconto: 300, valor: -300 })]), []);
});

test("vale com origem mas sem id de parcela também não é editável", () => {
  const sem = linhaVale(41, 300);
  (sem.origem as any).parcela_id = null;
  assert.deepEqual(verbasPagaveis([sem]), []);
});

test("sem valor digitado, a verba conta pelo previsto e não há diferença", () => {
  const verbas = verbasPagaveis(DETALHE);
  assert.equal(diferencaPagamento(verbas, {}), 0);
  assert.equal(temDiferenca(diferencaPagamento(verbas, {})), false);
});

test("descontar menos que o previsto dá diferença positiva e sobe o líquido na mesma medida", () => {
  const verbas = verbasPagaveis(DETALHE);
  const diferenca = diferencaPagamento(verbas, { 41: 100 });
  assert.equal(diferenca, 200);
  assert.equal(liquidoComDiferenca(2430, diferenca), 2630);
});

test("descontar mais que o previsto dá diferença negativa e desce o líquido", () => {
  const verbas = verbasPagaveis(DETALHE);
  const diferenca = diferencaPagamento(verbas, { 41: 500 });
  assert.equal(diferenca, -200);
  assert.equal(liquidoComDiferenca(2430, diferenca), 2230);
});

test("diferença de meio centavo não é diferença — não abre decisão nenhuma", () => {
  const verbas = verbasPagaveis(DETALHE);
  assert.equal(temDiferenca(diferencaPagamento(verbas, { 41: 299.998 })), false);
  assert.deepEqual(decisoesDisponiveis(diferencaPagamento(verbas, { 41: 299.998 })), []);
});

test("descontando menos, as três decisões do dono", () => {
  assert.deepEqual(decisoesDisponiveis(200), ["abater", "desconsiderar", "reparcelar"]);
});

test("descontando MAIS, exatamente duas opções — reparcelar e acréscimo avulso, e só elas", () => {
  // O pedido é literal ("passa a oferecer exatamente duas opções"), e o "só
  // elas" é a metade que importa: abater e desconsiderar não cabem porque não
  // existe valor deixado de cobrar — o dinheiro foi descontado de verdade.
  assert.deepEqual(decisoesDisponiveis(-200), ["reparcelar", "acrescimo_avulso"]);
  assert.equal(decisoesDisponiveis(-200).length, 2);
  assert.ok(!decisoesDisponiveis(-200).includes("abater"));
  assert.ok(!decisoesDisponiveis(-200).includes("desconsiderar"));
});

test("acréscimo avulso passa na conferência de quem descontou a mais", () => {
  assert.equal(erroDoPagamento(-200, "acrescimo_avulso", { dataPagamento: "2026-08-05" }), null);
});

test("acréscimo avulso NÃO cabe a quem descontou a menos", () => {
  const erro = erroDoPagamento(200, "acrescimo_avulso", { dataPagamento: "2026-08-05" });
  assert.ok(erro && erro.includes("não cabe"));
});

test("confirmar com diferença e sem decisão é recusado", () => {
  assert.equal(
    erroDoPagamento(200, null, { dataPagamento: "2026-08-05" }),
    "Há diferença entre o previsto e o pago. Escolha o que fazer com ela antes de confirmar.",
  );
});

test("sem diferença, confirma sem decisão nenhuma", () => {
  assert.equal(erroDoPagamento(0, null, { dataPagamento: "2026-08-05" }), null);
});

test("abater não é oferecido a quem descontou a mais, e é recusado se vier assim mesmo", () => {
  const erro = erroDoPagamento(-200, "abater", { dataPagamento: "2026-08-05" });
  assert.ok(erro && erro.includes("descontada a mais"));
});

test("reparcelar sem número de parcelas é recusado", () => {
  assert.equal(
    erroDoPagamento(200, "reparcelar", { dataPagamento: "2026-08-05" }),
    "Informe em quantas parcelas a diferença será dividida.",
  );
  assert.equal(erroDoPagamento(200, "reparcelar", { dataPagamento: "2026-08-05", parcelas: 2 }), null);
});

test("sem data do pagamento não se confirma — nem sem diferença", () => {
  assert.equal(erroDoPagamento(0, null, {}), "Informe a data do pagamento.");
});

// ===========================================================================
// A COLUNA DE EDIÇÃO — os dois estados por verba
// ===========================================================================
const DETALHE_COMPLETO: LinhaHolerite[] = [
  linha({ tipo: "bruto", descricao: "Salário", provento: 3000, valor: 3000 }),
  linha({ tipo: "inss", descricao: "INSS", desconto: 270, valor: -270 }),
  linha({ tipo: "ir", descricao: "IR", desconto: 100, valor: -100 }),
  linhaVale(41, 300),
  linha({ tipo: "outros", descricao: "Outros descontos", desconto: 50, valor: -50 }),
  linhaRubrica(9, 500),                                                      // bonificação → livre
  linhaRubrica(10, 200, { alteracao: "contratual", codigo: "reembolso" }),   // reembolso   → cadeado
  linha({ tipo: "liquido", descricao: "Líquido", valor: 2880 }),
];

test("cada verba ganha uma das duas classes — e o líquido não é verba nenhuma", () => {
  const verbas = verbasDaFolha(DETALHE_COMPLETO);
  assert.deepEqual(
    verbas.map((v) => [v.chave, v.classe]),
    [
      ["salario", "salario"],
      ["inss", "contratual"],
      ["ir", "contratual"],
      ["vale:41", "livre"],
      ["outros", "livre"],
      ["rubrica:9", "livre"],
      ["rubrica:10", "contratual"],
    ],
  );
});

test("a classe da rubrica vem do servidor, nunca de uma lista escrita na tela", () => {
  // A MESMA rubrica (bonificação, natureza salarial) muda de estado só porque
  // o catálogo do servidor mudou o campo `alteracao` — é isso que garante que
  // a tela e o servidor não possam discordar.
  assert.equal(verbaDaLinha(linhaRubrica(9, 500, { alteracao: "livre" }))!.classe, "livre");
  assert.equal(verbaDaLinha(linhaRubrica(9, 500, { alteracao: "contratual" }))!.classe, "contratual");
});

test("rubrica de discriminação antiga, sem o campo `alteracao`, cai em cadeado", () => {
  const antiga = linhaRubrica(9, 500);
  delete (antiga.origem as any).alteracao;
  assert.equal(verbaDaLinha(antiga)!.classe, "contratual");
});

test("linha que este módulo não conhece não vira verba — sem classe, sem botão, sem edição", () => {
  assert.equal(verbaDaLinha(linha({ tipo: "liquido", descricao: "Líquido", valor: 2880 })), null);
  assert.equal(verbaDaLinha(linha({ tipo: "ferias", descricao: "Férias", provento: 1000, valor: 1000 })), null);
});

test("o líquido acompanha TODAS as verbas: desconto sobe, vencimento desce e vice-versa", () => {
  const verbas = verbasDaFolha(DETALHE_COMPLETO);
  // Descontar R$ 100 a menos de vale sobe o líquido em R$ 100…
  assert.equal(liquidoComAlteracoes(2880, verbas, { "vale:41": 200 }), 2980);
  // …e lançar R$ 100 a mais de bonificação sobe outros R$ 100.
  assert.equal(liquidoComAlteracoes(2880, verbas, { "vale:41": 200, "rubrica:9": 600 }), 3080);
  // Reter R$ 30 a mais de INSS desce o líquido em R$ 30.
  assert.equal(liquidoComAlteracoes(2880, verbas, { inss: 300 }), 2850);
  // Sem nada digitado, o líquido é o previsto.
  assert.equal(liquidoComAlteracoes(2880, verbas, {}), 2880);
});

// ── O cadeado: avisa, não bloqueia ─────────────────────────────────────────
test("verba contratual alterada sem confirmar o cadeado é recusada antes de mandar", () => {
  const verbas = verbasDaFolha(DETALHE_COMPLETO);
  const erro = erroDasAlteracoes(verbas, { "rubrica:10": 250 }, new Set());
  assert.ok(erro && erro.includes("cadeado"));
});

test("confirmado o cadeado, a alteração passa — o cadeado avisa, não proíbe", () => {
  const verbas = verbasDaFolha(DETALHE_COMPLETO);
  assert.equal(erroDasAlteracoes(verbas, { "rubrica:10": 250 }, new Set(["rubrica:10"])), null);
});

test("verba livre nunca pede confirmação", () => {
  const verbas = verbasDaFolha(DETALHE_COMPLETO);
  assert.equal(erroDasAlteracoes(verbas, { "rubrica:9": 700, "vale:41": 100, outros: 80 }, new Set()), null);
});

test("verba contratual NÃO alterada não pede confirmação nenhuma", () => {
  const verbas = verbasDaFolha(DETALHE_COMPLETO);
  assert.equal(erroDasAlteracoes(verbas, { "rubrica:10": 200, inss: 270 }, new Set()), null);
});

// ── O salário ──────────────────────────────────────────────────────────────
test("direção do salário: igual dentro de meio centavo, maior, menor", () => {
  assert.equal(direcaoDoSalario(3000, 3000), "igual");
  assert.equal(direcaoDoSalario(3000, 3000.004), "igual");
  assert.equal(direcaoDoSalario(3000, 3200), "maior");
  assert.equal(direcaoDoSalario(3000, 2999), "menor");
});

test("salário para MENOR é recusado com a frase exata — e nem confirmar o cadeado salva", () => {
  const verbas = verbasDaFolha(DETALHE_COMPLETO);
  // Sem confirmação…
  assert.equal(erroDasAlteracoes(verbas, { salario: 2500 }, new Set()), MENSAGEM_SALARIO_MENOR);
  // …e COM confirmação: alteração contratual lesiva ao empregado é nula
  // (CLT, art. 468), então não existe consentimento que a valide.
  assert.equal(erroDasAlteracoes(verbas, { salario: 2500 }, new Set(["salario"])), MENSAGEM_SALARIO_MENOR);
});

test("a frase e a nota da recusa são as que o dono ditou, palavra por palavra", () => {
  assert.equal(
    MENSAGEM_SALARIO_MENOR,
    "O valor informado é inferior ao salário do funcionário. Não é permitida a alteração contratual lesiva.",
  );
  assert.equal(
    NOTA_SALARIO_MENOR,
    "a alteração do salário do funcionário para o valor informado deverá ser feita diretamente em "
    + "Administração > Configurações > Cadastro > Pessoas > Editar cadastro do funcionário > Salário-base (R$).",
  );
});

test("salário para MAIOR passa, uma vez confirmado o cadeado", () => {
  const verbas = verbasDaFolha(DETALHE_COMPLETO);
  assert.ok(erroDasAlteracoes(verbas, { salario: 3500 }, new Set())); // falta confirmar
  assert.equal(erroDasAlteracoes(verbas, { salario: 3500 }, new Set(["salario"])), null);
});

// ── O que viaja para o servidor ────────────────────────────────────────────
test("só o que MUDOU viaja, e cada verba no campo certo do payload", () => {
  const verbas = verbasDaFolha(DETALHE_COMPLETO);
  const payload = alteracoesDoPagamento(
    verbas,
    { salario: 3500, inss: 300, "rubrica:9": 600, "rubrica:10": 200, outros: 80, "vale:41": 300 },
    new Set(["salario", "inss"]),
  );
  assert.deepEqual(payload.rubricas, [{ rubrica_id: 9, valor_pago: 600, confirmado: false }]);
  assert.deepEqual(payload.retencoes, [{ tipo: "inss", valor_pago: 300, confirmado: true }]);
  assert.deepEqual(payload.salario, { valor_pago: 3500, confirmado: true });
  assert.deepEqual(payload.outros_descontos, { valor_pago: 80 });
});

test("sem alteração nenhuma, o payload vai vazio — nada de mandar linha intocada", () => {
  const verbas = verbasDaFolha(DETALHE_COMPLETO);
  const payload = alteracoesDoPagamento(verbas, {}, new Set());
  assert.deepEqual(payload.rubricas, []);
  assert.deepEqual(payload.retencoes, []);
  assert.equal(payload.salario, undefined);
  assert.equal(payload.outros_descontos, undefined);
});
