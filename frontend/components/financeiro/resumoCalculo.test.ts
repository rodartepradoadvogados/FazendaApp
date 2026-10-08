// Testes das contas puras da tela Resumo (components/financeiro/resumoCalculo.ts).
// Runner nativo do Node, igual aos de lib/:
//   node --experimental-strip-types --test components/financeiro/resumoCalculo.test.ts
import { test } from "node:test";
import assert from "node:assert/strict";
import type { Lanc } from "../../lib/financeiroTipos.ts";
import * as sit from "../../lib/financeiroSituacao.ts";
import {
  abertasPagar, abreviar, colunasGrafico, dataPorExtenso, diasAte, diasValidos, drill, faturaFechandoEmBreve,
  ordenarFaturas, posicao, proximaParcelaContrato, quandoVence, somaDias, topoEixo, vencidaMaisAntiga, type FaturaMin,
} from "./resumoCalculo.ts";

let seq = 0;
function lanc(p: Partial<Lanc>): Lanc {
  seq++;
  return {
    id: seq, numero_lancamento: `LC-2026-${String(seq).padStart(5, "0")}`, tipo: "despesa", valor: 100, valor_pago: null,
    desconto_acrescimo: 0, centro_custo: "Leite", codigo_conta: "3", conta_completa: "3.01.01", descricao: "Nota", fornecedor: "Posto Mil",
    responsavel: null, tipo_documento: "NF", numero_documento: String(1000 + seq), numero_os_orcamento: null, numero_documento_pagamento: null,
    conta_bancaria: null, forma_pagamento: null, data_vencimento_cartao: null, entregue: null,
    parcela_num: 1, parcela_total: 1, data_competencia: null, data_pagamento: null, data_vencimento: "2026-10-07",
    data_emissao: "2026-09-20", mes_competencia: null, mes_caixa: null, itens: [], ...p,
  };
}
const HOJE = "2026-10-07"; // quarta-feira
const em = (n: number) => somaDias(HOJE, n);

test("contas de data idênticas às de lib/financeiroSituacao.ts (inclui virada de mês/ano e bissexto)", () => {
  for (const [iso, n] of [["2026-10-07", 0], ["2026-10-07", -1], ["2026-10-31", 1], ["2026-12-31", 1], ["2028-02-28", 1], ["2026-03-01", -1], ["2026-10-07", 180]] as const) {
    assert.equal(somaDias(iso, n), sit.somaDias(iso, n));
    assert.equal(diasAte(somaDias(iso, n), iso), sit.diasAte(sit.somaDias(iso, n), iso));
  }
  assert.equal(somaDias("2026-10-31", 1), "2026-11-01");
  assert.equal(diasAte("2026-10-06", HOJE), -1);
});

test("só despesa sem pagamento entra em A pagar (nota de fatura incluída)", () => {
  const regs = [lanc({}), lanc({ data_pagamento: "2026-10-01", valor_pago: 100 }), lanc({ tipo: "receita" }), lanc({ fatura_id: 3 })];
  assert.equal(abertasPagar(regs).length, 2);
});

test("seletor Outro: inteiro de 1 a 180", () => {
  assert.equal(diasValidos("45"), 45);
  assert.equal(diasValidos(180), 180);
  assert.equal(diasValidos("0"), null);
  assert.equal(diasValidos("181"), null);
  assert.equal(diasValidos("12.5"), null);
  assert.equal(diasValidos(""), null);
  assert.equal(diasValidos("-3"), null);
});

test("gráfico diário: Vencidas + hoje até hoje+N, cores por janela", () => {
  const regs = [
    lanc({ data_vencimento: em(-10), valor: 50 }), lanc({ data_vencimento: em(-1), valor: 25 }),
    lanc({ data_vencimento: em(0), valor: 10 }), lanc({ data_vencimento: em(7), valor: 7 }),
    lanc({ data_vencimento: em(8), valor: 8 }), lanc({ data_vencimento: em(14), valor: 14 }), lanc({ data_vencimento: em(15), valor: 15 }),
  ];
  const cols = colunasGrafico(regs, HOJE, 14);
  assert.equal(cols.length, 1 + 15);
  assert.deepEqual([cols[0].rotulo, cols[0].valor, cols[0].n, cols[0].st], ["Vencidas", 75, 2, "venc"]);
  assert.equal(cols[0].ate, "2026-10-06");
  assert.deepEqual([cols[1].rotulo, cols[1].sub, cols[1].valor, cols[1].hoje], ["07", "hoje", 10, true]);
  assert.equal(cols[2].sub, "qui");
  assert.deepEqual([cols[8].valor, cols[8].st], [7, "logo"]);   // hoje+7
  assert.deepEqual([cols[9].valor, cols[9].st], [8, "aberto"]); // hoje+8
  assert.equal(cols[15].valor, 14);                              // hoje+14 entra
  const somaBarras = cols.slice(1).reduce((a, c) => a + c.valor, 0);
  assert.equal(somaBarras, posicao(regs, HOJE, 14, null).periodo.valor); // gráfico e Posição batem
});

test("gráfico semanal acima de 21 dias: uma barra por semana, a última mais curta", () => {
  const regs = [lanc({ data_vencimento: em(0), valor: 1 }), lanc({ data_vencimento: em(6), valor: 2 }), lanc({ data_vencimento: em(7), valor: 4 }),
    lanc({ data_vencimento: em(30), valor: 8 }), lanc({ data_vencimento: em(31), valor: 16 })];
  const cols = colunasGrafico(regs, HOJE, 30);
  // 31 dias (0..30) = 5 semanas: 0-6, 7-13, 14-20, 21-27, 28-30
  assert.equal(cols.length, 1 + 5);
  assert.deepEqual(cols.slice(1).map((c) => c.valor), [3, 4, 0, 0, 8]);
  assert.deepEqual([cols[1].sub, cols[1].st, cols[2].st, cols[3].st], ["sem. 1", "logo", "logo", "aberto"]);
  assert.deepEqual([cols[5].de, cols[5].ate], [em(28), em(30)]);
  assert.equal(cols[5].dica, "04/11 a 06/11");
  assert.equal(colunasGrafico([], HOJE, 21).length, 1 + 22); // 21 ainda é diário
  assert.equal(colunasGrafico([], HOJE, 22).length, 1 + 4);  // 23 dias = 4 semanas
});

test("posição: vencido, até 7, 8º ao Nº, período, depois, totais e saldo após pagar", () => {
  const regs = [
    lanc({ data_vencimento: em(-3), valor: 100 }),
    lanc({ data_vencimento: em(0), valor: 10 }), lanc({ data_vencimento: em(7), valor: 20 }),
    lanc({ data_vencimento: em(8), valor: 30 }), lanc({ data_vencimento: em(30), valor: 40 }),
    lanc({ data_vencimento: em(31), valor: 50 }), lanc({ data_vencimento: null, valor: 5 }),
    lanc({ data_vencimento: em(2), valor: 999, data_pagamento: em(-1), valor_pago: 999 }), // paga: fora
    lanc({ tipo: "receita", data_vencimento: em(4), valor: 300 }),
  ];
  const p = posicao(regs, HOJE, 30, 1000);
  assert.deepEqual(p.vencido, { valor: 100, n: 1 });
  assert.deepEqual(p.sem, { valor: 30, n: 2 });
  assert.deepEqual(p.meio, { valor: 70, n: 2 });
  assert.deepEqual(p.periodo, { valor: 100, n: 4 });
  assert.deepEqual(p.alem, { valor: 50, n: 1 });
  assert.deepEqual(p.semVencimento, { valor: 5, n: 1 });
  assert.deepEqual(p.aPagar, { valor: 255, n: 7 });
  assert.equal(p.vencido.valor + p.periodo.valor + p.alem.valor + p.semVencimento.valor, p.aPagar.valor);
  assert.deepEqual(p.aReceber, { valor: 300, n: 1 });
  assert.equal(p.saldoAposPagar, 1000 - 100 - 100);
  assert.equal(posicao(regs, HOJE, 30, null).saldoAposPagar, null);
});

test("posição com N ≤ 7: sem faixa do 8º dia; até 7 vira até N", () => {
  const regs = [lanc({ data_vencimento: em(5), valor: 10 }), lanc({ data_vencimento: em(6), valor: 20 })];
  const p = posicao(regs, HOJE, 5, 0);
  assert.equal(p.meio, null);
  assert.deepEqual(p.sem, { valor: 10, n: 1 });
  assert.deepEqual(p.periodo, p.sem);
  assert.deepEqual(p.alem, { valor: 20, n: 1 });
  assert.equal(p.saldoAposPagar, -10);
});

test("centavos exatos", () => {
  const p = posicao([lanc({ valor: 0.1 }), lanc({ valor: 0.2 })], HOJE, 7, 0.3);
  assert.equal(p.sem.valor, 0.3);
  assert.equal(p.saldoAposPagar, 0);
});

test("drill: de/até de cada linha", () => {
  assert.deepEqual(drill("venc", HOJE, 30), { tipo: "venc", ate: "2026-10-06", rotulo: "Vencido, até ontem" });
  assert.deepEqual(drill("sem", HOJE, 30), { tipo: "sem", de: HOJE, ate: "2026-10-14", rotulo: "Vence em até 7 dias" });
  assert.deepEqual(drill("meio", HOJE, 30), { tipo: "meio", de: "2026-10-15", ate: "2026-11-06", rotulo: "Vence do 8º ao 30º dia" });
  assert.deepEqual(drill("ate", HOJE, 30), { tipo: "ate", de: HOJE, ate: "2026-11-06", rotulo: "Vence em até 30 dias" });
  assert.deepEqual(drill("alem", HOJE, 30), { tipo: "alem", de: "2026-11-07", rotulo: "Vence depois de 06/11" });
  assert.deepEqual(drill("todas", HOJE, 30), { tipo: "todas", rotulo: "Todas em aberto" });
  assert.deepEqual(drill("sem", HOJE, 1), { tipo: "sem", de: HOJE, ate: "2026-10-08", rotulo: "Vence em até 1 dia" });
});

test("drill e posição contam as mesmas contas (filtro de vencimento de/até inclusivo)", () => {
  const regs = Array.from({ length: 60 }, (_, i) => lanc({ data_vencimento: em(i - 20), valor: i + 1 }));
  const N = 14;
  const p = posicao(regs, HOJE, N, 0);
  const filtra = (d: ReturnType<typeof drill>) => abertasPagar(regs).filter((l) => (!d.de || l.data_vencimento! >= d.de) && (!d.ate || l.data_vencimento! <= d.ate));
  const somaD = (d: ReturnType<typeof drill>) => filtra(d).reduce((a, l) => a + l.valor, 0);
  assert.equal(somaD(drill("venc", HOJE, N)), p.vencido.valor);
  assert.equal(somaD(drill("sem", HOJE, N)), p.sem.valor);
  assert.equal(somaD(drill("meio", HOJE, N)), p.meio!.valor);
  assert.equal(somaD(drill("ate", HOJE, N)), p.periodo.valor);
  assert.equal(somaD(drill("alem", HOJE, N)), p.alem.valor);
});

test("eixo e rótulos das barras", () => {
  assert.equal(topoEixo(0), 1000);
  assert.equal(topoEixo(6900), 8000);
  assert.equal(topoEixo(15338), 20000);
  assert.equal(topoEixo(1000), 1000);
  assert.equal(abreviar(5158), "5,2k");
  assert.equal(abreviar(1_250_000), "1,3 mi");
  assert.equal(abreviar(800), "800");
});

test("data por extenso no fuso local", () => {
  assert.equal(dataPorExtenso(HOJE), "Quarta-feira, 7 de outubro");
  assert.equal(dataPorExtenso(HOJE, false), "7 de outubro");
});

test("fila: vencida mais antiga, próxima parcela de contrato, quando vence", () => {
  const a = lanc({ data_vencimento: em(-2), valor: 10 });
  const b = lanc({ data_vencimento: em(-6), valor: 5 });
  const c = lanc({ data_vencimento: em(-6), valor: 50 });
  assert.equal(vencidaMaisAntiga([a, b, c], HOJE)?.id, c.id);
  assert.equal(vencidaMaisAntiga([lanc({ data_vencimento: em(1) })], HOJE), null);
  const k1 = lanc({ tipo_documento: "Contrato", data_vencimento: em(-1) });
  const k2 = lanc({ tipo_documento: "Empreitada", data_vencimento: em(9) });
  const k3 = lanc({ tipo_documento: "Contrato", data_vencimento: em(3) });
  const nf = lanc({ tipo_documento: "NF", data_vencimento: em(0) });
  assert.equal(proximaParcelaContrato([k1, k2, k3, nf], HOJE)?.id, k3.id);
  assert.equal(quandoVence(em(0), HOJE), "Vence hoje");
  assert.equal(quandoVence(em(1), HOJE), "Vence em 1 dia");
  assert.equal(quandoVence(em(-6), HOJE), "Venceu há 6 dias");
});

test("faturas: fechando em breve e ordem do painel", () => {
  const f = (p: Partial<FaturaMin>): FaturaMin => ({ id: ++seq, fornecedor: "Coop", rotulo: "FAT", status: "aberta", data_fechamento_prevista: null, data_vencimento: null, valor_total: 0, notas: 0, ...p });
  const longe = f({ data_fechamento_prevista: em(20) });
  const perto = f({ data_fechamento_prevista: em(5) });
  const atrasada = f({ data_fechamento_prevista: em(-1) });
  const fechada = f({ status: "fechada", data_vencimento: em(3) });
  const paga = f({ status: "paga", data_vencimento: em(-30) });
  assert.equal(faturaFechandoEmBreve([longe, perto], HOJE)?.id, perto.id);
  assert.equal(faturaFechandoEmBreve([longe, perto, atrasada], HOJE)?.id, atrasada.id);
  assert.equal(faturaFechandoEmBreve([longe, fechada], HOJE), null);
  assert.deepEqual(ordenarFaturas([paga, fechada, longe, perto]).map((x) => x.id), [perto.id, longe.id, fechada.id, paga.id]);
});
