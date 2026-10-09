import { test } from "node:test";
import assert from "node:assert/strict";
import {
  composicaoSubtotal, conferirCascata, degrausCascata, filtroConsultasDe, fraseDre, linhasDre, valorComSinal, valorLinha,
} from "./relatorioDre.ts";
import { brl, comparacaoDe, delta, periodoDe } from "./relatorioContexto.ts";

// Cascata do cenário da auditoria (mar/2031, regras v2, Pecuária Leiteira) — formato de GET /financeiro/dre.
const linha = (chave: string, rotulo: string, operador: string, valor: number, contas: { codigo: string | null; nome: string; valor: number }[] = []) =>
  ({ chave, rotulo, operador, eh_subtotal: operador === "=", valor, contas });
const DRE = (fator = 1) => ({
  periodo: { inicio: "2031-03-01", fim: "2031-03-31" }, regime: "competencia", centro_custo: "Pecuária Leiteira",
  receitas_total: 0, despesas_total: 0, resultado: 0,
  nao_classificado: { total: 2560, contas: [{ codigo: "(sem conta)", nome: "Folha", valor: 2560 }] },
  fora_da_dre: { total: 0, contas: [] }, depreciacao_periodo: { total: 1000, inconsistencias: [] },
  cascata: [
    linha("RECEITA_VENDAS", "Receita de vendas", "+", 10000 * fator, [{ codigo: "8.1", nome: "Venda de leite", valor: 10000 * fator }]),
    linha("DEDUCAO_IMPOSTOS", "Deduções de impostos", "-", 150, [{ codigo: "(descontos)", nome: "Funrural", valor: 150 }]),
    linha("RECEITA_LIQUIDA", "Receita líquida", "=", 10000 * fator - 150),
    linha("CUSTO_VARIAVEL", "Custo variável", "-", 7500, [{ codigo: "8.2", nome: "Ração", valor: 7000 }, { codigo: "8.21", nome: "Sal", valor: 500 }]),
    linha("MARGEM_BRUTA", "Margem bruta", "=", 10000 * fator - 7650),
    linha("DESPESA_VARIAVEL", "Despesas variáveis", "-", 0),
    linha("MARGEM_CONTRIBUICAO", "Margem de contribuição", "=", 10000 * fator - 7650),
    linha("GASTOS_PESSOAL", "Gastos com pessoal", "-", 1600, [{ codigo: "8.7", nome: "Mão de obra", valor: 1600 }]),
    linha("DESPESAS_OPERACIONAIS", "Despesas operacionais", "-", 0),
    linha("EBITDA", "EBITDA", "=", 10000 * fator - 9250),
    linha("DEPRECIACAO_AMORT_EXAUSTAO", "Depreciação", "-", 1000),
    linha("OUTRAS_REC_DESP", "Outras", "±", 0),
    linha("RESULTADO_OPERACIONAL", "EBIT", "=", 10000 * fator - 10250),
    linha("TRIBUTOS_IR_CSLL", "Tributos", "-", 0),
    linha("RESULTADO_LIQUIDO", "Resultado líquido", "=", 10000 * fator - 10250),
  ],
});

test("sinal pela regra do servidor: custo em magnitude, o operador subtrai", () => {
  assert.equal(valorComSinal("-", 150), -150);
  assert.equal(valorComSinal("+", 150), 150);
  assert.equal(valorComSinal("±", -40), -40);
});

test("linhas: nome em português simples, sinal, % da receita e comparação casada por conta", () => {
  const cmp = DRE(1.2);
  cmp.cascata[3] = linha("CUSTO_VARIAVEL", "Custo variável", "-", 7200, [{ codigo: "8.2", nome: "Ração", valor: 6900 }, { codigo: "8.3", nome: "Milho", valor: 300 }]);
  const ls = linhasDre(DRE() as never, cmp as never);
  const res = valorLinha(ls, "RESULTADO_LIQUIDO")!;
  assert.equal(res.nome, "Resultado"); assert.equal(res.a, -250); assert.equal(res.b, 1750);
  const ebitda = valorLinha(ls, "EBITDA")!;
  assert.equal(ebitda.nome, "Geração de caixa da atividade"); assert.equal(ebitda.tecnico, "EBITDA");
  const cv = valorLinha(ls, "CUSTO_VARIAVEL")!;
  assert.equal(cv.a, -7500); assert.equal(cv.b, -7200);
  assert.equal(Math.round(cv.pctReceita! * 1000) / 10, 76.1);
  // Ração casa com ração; Sal só existe agora; Milho só na comparação (aparece com zero).
  assert.deepEqual(cv.contas.map((c) => [c.nome, c.a, c.b]), [["Ração", -7000, -6900], ["Sal", -500, 0], ["Milho", 0, -300]]);
  // O detalhe fecha com o total da linha.
  assert.equal(cv.contas.reduce((s, c) => s + c.a, 0), cv.a);
  assert.equal(cv.contas.reduce((s, c) => s + (c.b ?? 0), 0), cv.b);
  // Sem comparação: b fica null (não zero).
  assert.equal(linhasDre(DRE() as never, null)[0].b, null);
  assert.deepEqual(linhasDre(null, null), []);
});

test("cascata em degraus: linha zero sai do gráfico, subtotal parte do zero, e a conta fecha", () => {
  const ls = linhasDre(DRE() as never, null);
  const ds = degrausCascata(ls);
  assert.ok(!ds.some((d) => d.chave === "DESPESA_VARIAVEL" || d.chave === "TRIBUTOS_IR_CSLL"));
  const ded = ds.find((d) => d.chave === "DEDUCAO_IMPOSTOS")!;
  assert.deepEqual([ded.ini, ded.fim], [10000, 9850]);
  const final = ds[ds.length - 1];
  assert.ok(final.resultado && final.subtotal && final.fim === -250);
  assert.deepEqual(conferirCascata(ls), { fecha: true, diferenca: 0 });
  // Subtotal que não bate com as linhas é denunciado.
  const torto = ls.map((l) => (l.chave === "EBITDA" ? { ...l, a: l.a + 10 } : l));
  assert.equal(conferirCascata(torto).fecha, false);
});

test("composição de um subtotal: do subtotal anterior até ele, sem linhas zeradas", () => {
  const ls = linhasDre(DRE() as never, null);
  assert.deepEqual(composicaoSubtotal(ls, "EBITDA").map((l) => l.chave), ["MARGEM_CONTRIBUICAO", "GASTOS_PESSOAL"]);
  assert.deepEqual(composicaoSubtotal(ls, "RECEITA_LIQUIDA").map((l) => l.chave), ["RECEITA_VENDAS", "DEDUCAO_IMPOSTOS"]);
});

test("frase-resumo escrita: ganhou/perdeu, comparação com sentido e pendência de classificação", () => {
  const per = periodoDe("m:2031-03")!;
  const c = comparacaoDe(per, "aa")!;
  const ls = linhasDre(DRE() as never, DRE(1.2) as never);
  const txt = fraseDre({ periodo: per, regime: "comp", linhas: ls, rotuloCmp: c.rotulo, brl: (v) => brl(v, 0), naoClassificadoContas: 1, delta })
    .map((t) => t.t).join("");
  assert.equal(txt, "Em março/2031, pelo mês do gasto, a fazenda perdeu R$ 250 (pior que mar/30, quando ganhou R$ 1.750). " +
    "A atividade gerou R$ 750 de caixa antes do desgaste dos bens e dos juros. 1 conta sem classificação ficou fora até serem classificadas.");
});

test("drill para Consultas: mesmo período, regime, centro e conta; pseudoconta não filtra", () => {
  const per = periodoDe("m:2031-03")!;
  assert.deepEqual(filtroConsultasDe({ periodo: per, regime: "caixa", cc: "Pecuária Leiteira", conta: { codigo: "8.2", nome: "Ração" }, origem: "DRE" }), {
    de: "2031-03-01", ate: "2031-03-31", periodoPor: "pagamento", centro: "Pecuária Leiteira", conta: "8.2", contaNome: "Ração", origem: "DRE",
  });
  const f = filtroConsultasDe({ periodo: per, regime: "comp", cc: "todos", conta: { codigo: "(descontos)", nome: "Funrural" }, origem: "DRE" });
  assert.equal(f.periodoPor, "competencia"); assert.equal(f.conta, undefined); assert.equal(f.centro, undefined);
});
