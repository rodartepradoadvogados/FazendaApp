// Testes de frontend/lib/pagamentoFolhaRegras.ts — o pop-up de pagar com
// valor distinto numa verba. Rodam com o runner nativo do Node: `npm test`.
//
// O que estas regras existem para impedir, e que estes testes travam:
//  - confirmar um pagamento com diferença e sem decisão escolhida (é o pedido
//    literal do dono, e é o que impede congelar um recibo que cobra um
//    desconto que não houve);
//  - oferecer "abater" ou "a fazenda assume" para quem descontou a MAIS — não
//    há valor deixado de cobrar nesses casos;
//  - tornar editável uma verba que não é dívida da pessoa (salário, INSS, IR,
//    rubrica): as três decisões não significam nada sobre elas.
import { test } from "node:test";
import assert from "node:assert/strict";
import type { LinhaHolerite } from "./api.ts";
import {
  decisoesDisponiveis, diferencaPagamento, erroDoPagamento, liquidoComDiferenca, temDiferenca,
  verbasPagaveis,
} from "./pagamentoFolhaRegras.ts";

function linha(over: Partial<LinhaHolerite>): LinhaHolerite {
  return {
    label: "x", valor: 0, tipo: "bruto", descricao: "x", referencia: "",
    provento: null, desconto: null, origem: null, ...over,
  } as LinhaHolerite;
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

test("só a parcela de vale é verba editável — salário, INSS e líquido não são dívida da pessoa", () => {
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

test("descontando menos, as três decisões do dono; descontando mais, só reparcelar", () => {
  assert.deepEqual(decisoesDisponiveis(200), ["abater", "desconsiderar", "reparcelar"]);
  assert.deepEqual(decisoesDisponiveis(-200), ["reparcelar"]);
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
