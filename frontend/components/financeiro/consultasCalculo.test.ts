// Testes das contas puras da tela Consultas (components/financeiro/consultasCalculo.ts).
// Runner nativo do Node, igual aos de lib/:
//   node --experimental-strip-types --test components/financeiro/consultasCalculo.test.ts
import { test } from "node:test";
import assert from "node:assert/strict";
import type { Lanc } from "../../lib/financeiroTipos.ts";
import { casaBusca } from "../../lib/busca.ts";
import {
  filtrosPadrao, aplicarFiltroInicial, periodoMesCorrente, realizado, valorDoItem, filtrarRealizados,
  resumir, contarFiltrosAtivos, montarLivro, ordenarLinhas, type FiltrosConsulta,
} from "./consultasCalculo.ts";

let seq = 0;
function lanc(p: Partial<Lanc>): Lanc {
  seq++;
  return {
    id: seq, numero_lancamento: `LC-2026-${String(seq).padStart(5, "0")}`, tipo: "despesa", valor: 100, valor_pago: 100,
    desconto_acrescimo: 0, centro_custo: "Leite", codigo_conta: "3", conta_completa: "3.01.01", descricao: "Nota", fornecedor: "Posto Mil",
    responsavel: null, tipo_documento: "NF", numero_documento: String(1000 + seq), numero_os_orcamento: null, numero_documento_pagamento: null,
    conta_bancaria: "Banco do Brasil", forma_pagamento: "pix", data_vencimento_cartao: null, entregue: null,
    parcela_num: 1, parcela_total: 1, data_competencia: null, data_pagamento: "2026-10-05", data_vencimento: "2026-10-05",
    data_emissao: "2026-09-20", mes_competencia: null, mes_caixa: null, itens: [], ...p,
  };
}
const item = (produto: string, valor_total: number) => ({
  id: ++seq, produto, valor_total, eh_vale: false, vale_tipo: null, vale_id: null, vale_pessoa_id: null, vale_pessoa_nome: null,
});
const HOJE = "2026-10-07";
const base = (p: Partial<FiltrosConsulta> = {}): FiltrosConsulta => ({ ...filtrosPadrao(HOJE), ...p });

test("período padrão: pagamento, mês corrente inteiro (fuso local, sem UTC)", () => {
  assert.deepEqual(periodoMesCorrente("2026-10-07"), { de: "2026-10-01", ate: "2026-10-31" });
  assert.deepEqual(periodoMesCorrente("2028-02-10"), { de: "2028-02-01", ate: "2028-02-29" });
  const f = filtrosPadrao(HOJE);
  assert.equal(f.periodoPor, "pagamento");
  assert.equal(f.movimento, "ambos");
});

test("só o realizado: nada sem data de pagamento aparece", () => {
  const regs = [lanc({}), lanc({ data_pagamento: null, valor_pago: null })];
  const xs = filtrarRealizados(regs, base(), casaBusca);
  assert.equal(xs.length, 1);
  assert.equal(xs[0].l.id, regs[0].id);
});

test("realizado = valor_pago, não valor (baixa parcial com reparcelamento)", () => {
  const parcial = lanc({ valor: 1000, valor_pago: 400, desconto_acrescimo: 0 });
  assert.equal(realizado(parcial), 400);
  assert.equal(realizado(lanc({ valor: 250, valor_pago: null })), 250); // só cai no valor se valor_pago for null
  const r = resumir(filtrarRealizados([parcial], base(), casaBusca), "ambos");
  assert.equal(r.totalPago, 400);
});

test("cards: pago, recebido, resultado, quantidade e desconto/acréscimo", () => {
  const regs = [
    lanc({ tipo: "despesa", valor: 100, valor_pago: 95, desconto_acrescimo: -5 }),
    lanc({ tipo: "despesa", valor: 200, valor_pago: 202.5, desconto_acrescimo: 2.5 }),
    lanc({ tipo: "receita", valor: 1000, valor_pago: 1000, conta_completa: "2.01" }),
  ];
  const r = resumir(filtrarRealizados(regs, base(), casaBusca), "ambos");
  assert.equal(r.totalPago, 297.5);
  assert.equal(r.totalRecebido, 1000);
  assert.equal(r.resultado, 702.5);
  assert.equal(r.quantidade, 3);
  assert.equal(r.qtdPagamentos, 2);
  assert.equal(r.descontoAcrescimo, -2.5);
  assert.equal(r.acrescimos, 2.5);
  assert.equal(r.descontos, 5);
});

test("top contas gerenciais: 3 maiores pelo realizado (despesas, ou receitas no filtro Recebimento)", () => {
  const regs = [
    lanc({ conta_completa: "3.01", valor_pago: 50 }), lanc({ conta_completa: "3.02", valor_pago: 300 }),
    lanc({ conta_completa: "3.03", valor_pago: 120 }), lanc({ conta_completa: "3.04", valor_pago: 10 }),
    lanc({ conta_completa: "3.01", valor_pago: 100 }),
    lanc({ tipo: "receita", conta_completa: "2.01", valor_pago: 9999 }),
  ];
  const r = resumir(filtrarRealizados(regs, base(), casaBusca), "ambos");
  assert.deepEqual(r.topContas, [{ codigo: "3.02", valor: 300 }, { codigo: "3.01", valor: 150 }, { codigo: "3.03", valor: 120 }]);
  const rr = resumir(filtrarRealizados(regs, base({ movimento: "recebimento" }), casaBusca), "recebimento");
  assert.deepEqual(rr.topContas, [{ codigo: "2.01", valor: 9999 }]);
});

test("filtro de produto soma só o ITEM, não a nota inteira", () => {
  const nota = lanc({ valor: 1000, valor_pago: 1000, itens: [item("Diesel S10", 700), item("Óleo 15W40", 300)] });
  const outra = lanc({ valor: 80, valor_pago: 80, itens: [item("Sêmen", 80)] });
  const xs = filtrarRealizados([nota, outra], base({ produto: "diesel s10" }), casaBusca);
  assert.equal(xs.length, 1);
  assert.equal(xs[0].valor, 700);
  assert.equal(xs[0].soItem, true);
  assert.equal(resumir(xs, "ambos").totalPago, 700);
  // sem filtro de produto, a nota conta inteira
  assert.equal(resumir(filtrarRealizados([nota], base(), casaBusca), "ambos").totalPago, 1000);
});

test("item numa parcela / baixa parcial: mesma proporção do que foi pago nesta linha", () => {
  // Parcela 1/2 de uma nota de 1000 (itens são da nota inteira): pagou 500.
  const parcela = lanc({ valor: 500, valor_pago: 500, parcela_num: 1, parcela_total: 2, itens: [item("Diesel", 700), item("Óleo", 300)] });
  assert.equal(valorDoItem(parcela, "Diesel"), 350);
  // Baixa parcial: nota de 1000, pagou 400 (o resto foi reparcelado).
  const parcial = lanc({ valor: 1000, valor_pago: 400, itens: [item("Diesel", 700), item("Óleo", 300)] });
  assert.equal(valorDoItem(parcial, "Diesel"), 280);
});

test("período por emissão, vencimento ou pagamento usa o campo certo", () => {
  const l = lanc({ data_emissao: "2026-08-15", data_vencimento: "2026-09-10", data_pagamento: "2026-10-02" });
  const ago = { de: "2026-08-01", ate: "2026-08-31" }, set = { de: "2026-09-01", ate: "2026-09-30" }, out = { de: "2026-10-01", ate: "2026-10-31" };
  assert.equal(filtrarRealizados([l], base({ periodoPor: "emissao", ...ago }), casaBusca).length, 1);
  assert.equal(filtrarRealizados([l], base({ periodoPor: "emissao", ...out }), casaBusca).length, 0);
  assert.equal(filtrarRealizados([l], base({ periodoPor: "vencimento", ...set }), casaBusca).length, 1);
  assert.equal(filtrarRealizados([l], base({ periodoPor: "vencimento", ...out }), casaBusca).length, 0);
  assert.equal(filtrarRealizados([l], base({ periodoPor: "pagamento", ...out }), casaBusca).length, 1);
  assert.equal(filtrarRealizados([l], base({ periodoPor: "pagamento", ...set }), casaBusca).length, 0);
  // Sem a data do campo escolhido, fica fora quando há período.
  const semEmissao = lanc({ data_emissao: null });
  assert.equal(filtrarRealizados([semEmissao], base({ periodoPor: "emissao", ...out }), casaBusca).length, 0);
});

test("demais filtros: movimento, centro, conta bancária, documento (nº doc, lançamento, OS), fornecedor, conta gerencial", () => {
  const a = lanc({ tipo: "despesa", centro_custo: "Leite", conta_bancaria: "Sicoob", numero_documento: "4521", fornecedor: "Posto Mil", conta_completa: "3.01.02" });
  const b = lanc({ tipo: "receita", centro_custo: "Corte", conta_bancaria: "Banco do Brasil", numero_os_orcamento: "OS-77", fornecedor: "Laticínio", conta_completa: "2.01" });
  const f = (p: Partial<FiltrosConsulta>) => filtrarRealizados([a, b], base(p), casaBusca).map((x) => x.l.id);
  assert.deepEqual(f({ movimento: "pagamento" }), [a.id]);
  assert.deepEqual(f({ movimento: "recebimento" }), [b.id]);
  assert.deepEqual(f({ centro: "Corte" }), [b.id]);
  assert.deepEqual(f({ banco: "Sicoob" }), [a.id]);
  assert.deepEqual(f({ documento: "452" }), [a.id]);
  assert.deepEqual(f({ documento: "os77" }), [b.id]);
  assert.deepEqual(f({ documento: b.numero_lancamento! }), [b.id]);
  assert.deepEqual(f({ fornecedor: "Laticínio" }), [b.id]);
  assert.deepEqual(f({ conta: "3.01" }), [a.id]); // subárvore
  assert.deepEqual(f({ conta: "3.0" }), []);      // prefixo solto não casa
});

test("filtro inicial por documento abre o período; contagem de filtros ativos", () => {
  const p = filtrosPadrao(HOJE);
  const ini = aplicarFiltroInicial(p, { documento: "LC-2026-00012", banco: "Sicoob" });
  assert.equal(ini.de, ""); assert.equal(ini.ate, "");
  assert.equal(ini.banco, "Sicoob");
  assert.equal(contarFiltrosAtivos(p, p), 0);
  assert.equal(contarFiltrosAtivos(ini, p), 3); // documento + banco + período
  assert.equal(contarFiltrosAtivos({ ...p, movimento: "pagamento", produto: "Diesel" }, p), 2);
});

test("livro caixa: saldo acumulado SÓ com conta bancária escolhida", () => {
  const regs = [
    lanc({ tipo: "receita", valor_pago: 1000, conta_bancaria: "BB", data_pagamento: "2026-09-20" }), // antes do período
    lanc({ tipo: "despesa", valor_pago: 200, conta_bancaria: "BB", data_pagamento: "2026-10-03" }),
    lanc({ tipo: "receita", valor: 600, valor_pago: 500, conta_bancaria: "BB", data_pagamento: "2026-10-01" }),
    lanc({ tipo: "despesa", valor_pago: 999, conta_bancaria: "Sicoob", data_pagamento: "2026-10-02" }), // outra conta
    lanc({ tipo: "despesa", valor_pago: 50, conta_bancaria: "BB", data_pagamento: null }), // em aberto
  ];
  // Sem conta: lista cronológica, sem saldo nenhum.
  const fSem = base();
  const sem = montarLivro(regs, filtrarRealizados(regs, fSem, casaBusca), fSem);
  assert.equal(sem.saldoAnterior, null);
  assert.equal(sem.saldoFinal, null);
  assert.ok(sem.linhas.every((x) => x.saldo === null));
  assert.deepEqual(sem.linhas.map((x) => x.l.data_pagamento), ["2026-10-01", "2026-10-02", "2026-10-03"]);

  // Com conta: parte do saldo realizado antes do período e acumula pelo valor_pago.
  const fBB = base({ banco: "BB", fornecedor: "Ignorado no livro" });
  const com = montarLivro(regs, filtrarRealizados(regs, fBB, casaBusca), fBB);
  assert.equal(com.saldoAnterior, 1000);
  assert.deepEqual(com.linhas.map((x) => [x.entrada, x.saida, x.saldo]), [[500, 0, 1500], [0, 200, 1300]]);
  assert.equal(com.saldoFinal, 1300);
  assert.equal(com.totalEntradas, 500);
  assert.equal(com.totalSaidas, 200);
});

test("livro caixa (regras v2): parte do saldo de abertura e ignora a nota que só classifica o cartão", () => {
  const regs = [
    lanc({ tipo: "despesa", valor_pago: 300, conta_bancaria: "BB", data_pagamento: "2026-09-25" }), // antes da abertura: já está nela
    lanc({ tipo: "despesa", valor_pago: 200, conta_bancaria: "BB", data_pagamento: "2026-10-03" }),
    lanc({ tipo: "despesa", valor: 700, valor_pago: null, conta_bancaria: "BB", data_pagamento: "2026-10-04" }), // L6: vale o valor
    lanc({ tipo: "despesa", valor_pago: 800, conta_bancaria: "BB", data_pagamento: "2026-10-05", gerado_por: "backfill_cartao" }),
  ];
  const fBB = base({ banco: "BB" });
  const livro = montarLivro(regs, filtrarRealizados(regs, fBB, casaBusca), fBB, { saldo: 5000, data: "2026-09-30" });
  assert.equal(livro.saldoAnterior, 5000);
  assert.deepEqual(livro.linhas.map((x) => x.saida), [200, 700]);
  assert.equal(livro.saldoFinal, 4100);
  // Sem abertura (regras antigas): como antes, desde o primeiro lançamento.
  assert.equal(montarLivro(regs, filtrarRealizados(regs, fBB, casaBusca), fBB).saldoFinal, -1200);
});

test("ordenação: valor e data, asc/desc, sem mutar a lista", () => {
  const xs = filtrarRealizados([
    lanc({ valor_pago: 30, data_pagamento: "2026-10-03" }), lanc({ valor_pago: 10, data_pagamento: "2026-10-01" }), lanc({ valor_pago: 20, data_pagamento: "2026-10-02" }),
  ], base(), casaBusca);
  const antes = xs.map((x) => x.valor);
  assert.deepEqual(ordenarLinhas(xs, { chave: "valor", dir: "asc" }).map((x) => x.valor), [10, 20, 30]);
  assert.deepEqual(ordenarLinhas(xs, { chave: "data", dir: "desc" }).map((x) => x.l.data_pagamento), ["2026-10-03", "2026-10-02", "2026-10-01"]);
  assert.deepEqual(xs.map((x) => x.valor), antes);
});

test("folha gerada pelo sistema aparece em Consultas e a soma por conta fecha com o realizado (Fase A, PR 2/3)", () => {
  // A nota da folha (líquido 2.560 pago) com os itens da folha pelo bruto: a
  // tela lista a NOTA pelo realizado; os itens (bruto e redutores) somam o líquido.
  const folha = lanc({
    tipo_documento: "Folha de pagamento", origem: "auto", conta_completa: "3.03.01.01", codigo_conta: "3",
    valor: 2560, valor_pago: 2560, fornecedor: "Ana Teste",
    itens: [
      { ...item("Salário e verbas", 3000), gerado_por: "folha_salario", codigo_conta_gerencial: "3.03.01.01" },
      { ...item("(−) INSS e IRRF retidos", -240), gerado_por: "folha_retidos", natureza_fin: "OBRIGACAO" },
      { ...item("(−) Vale descontado", -200), gerado_por: "folha_vale", natureza_fin: "ADIANTAMENTO" },
    ],
  });
  const xs = filtrarRealizados([folha, lanc({})], base({ conta: "3.03.01.01" }), casaBusca);
  assert.equal(xs.length, 1);
  assert.equal(xs[0].l.origem, "auto");
  assert.equal(xs[0].valor, 2560);
  assert.equal((folha.itens || []).reduce((s, it) => s + it.valor_total, 0), 2560);
  assert.deepEqual(resumir(xs, "pagamento").topContas, [{ codigo: "3.03.01.01", valor: 2560 }]);
});
