import { test } from "node:test";
import assert from "node:assert/strict";
import {
  aplicarPercentual, aplicarSemOrcamento, avaliar, celulasAlteradas, contasForaDoPlano, copiarAnoAnterior, desvioPorLinha,
  fraseOrcamento, lerValor, montarGrade, periodoDeMesesInteiros, preencherLinha, secoesContas, totaisGrade,
  type LinhaCascataOrc, type LinhaConta, type RespostaOrcamento,
} from "./relatorioOrcamento.ts";
import { brl, delta, periodoDe } from "./relatorioContexto.ts";

const L = (o: Partial<LinhaConta>): LinhaConta => ({
  codigo_conta_gerencial: "x", nome_conta_gerencial: "X", tipo: "despesa", orcado: 0, realizado: 0, grupo: "despesa_operacional",
  coberta_por: null, cobre: [], desvio: null, desvio_pct: null, situacao: "sem_orcamento", linha_dre: null, ...o,
});
const T = (rotulo: string, orcado: number, realizado: number) => ({ rotulo, orcado, realizado, desvio: orcado ? realizado - orcado : null, desvio_pct: null, situacao: "sem_orcamento" as const });
const RESP: RespostaOrcamento = {
  periodo: { inicio: "2026-09-01", fim: "2026-09-30" }, centro_custo: null, regime: "competencia", tem_orcamento: true,
  meses: ["2026-09"], meses_com_orcamento: ["2026-09"], regras_v2: true,
  linhas: [
    L({ codigo_conta_gerencial: "8.1", nome_conta_gerencial: "Leite", tipo: "receita", grupo: "receita", orcado: 48500, realizado: 47401.2, desvio: -1098.8, situacao: "desfavoravel" }),
    L({ codigo_conta_gerencial: "8", nome_conta_gerencial: "Grupo", orcado: 2000, realizado: 1600, desvio: -400, situacao: "favoravel", cobre: ["8.7"] }),
    L({ codigo_conta_gerencial: "8.7", nome_conta_gerencial: "Mão de obra", realizado: 1600, coberta_por: "8", situacao: "coberta_pelo_grupo" }),
    L({ codigo_conta_gerencial: "8.12", nome_conta_gerencial: "Sanidade", realizado: 1470 }),
    L({ codigo_conta_gerencial: "8.4", nome_conta_gerencial: "Principal", realizado: 3500, grupo: "fora_do_resultado", situacao: "fora_do_resultado" }),
  ],
  totais: { receita: T("Receitas", 48500, 47401.2), deducao: T("Deduções", 0, 0), despesa_operacional: T("Despesas operacionais", 2000, 3070), fora_do_resultado: T("Fora", 0, 3500) },
  linhas_dre: [
    { chave: "RECEITA_VENDAS", rotulo: "R", operador: "+", eh_subtotal: false, realizado: 47401.2, orcado: 48500, origem_orcado: "orcamento", realizado_l: 2.52, orcado_l: 2.5784 },
    { chave: "CUSTO_VARIAVEL", rotulo: "C", operador: "-", eh_subtotal: false, realizado: 19378.06, orcado: 20600, origem_orcado: "orcamento", realizado_l: 1.0302, orcado_l: 1.0952 },
    { chave: "DESPESA_VARIAVEL", rotulo: "D", operador: "-", eh_subtotal: false, realizado: 1470, orcado: null, origem_orcado: null, realizado_l: 0.0781, orcado_l: null },
    { chave: "DEPRECIACAO_AMORT_EXAUSTAO", rotulo: "Dep", operador: "-", eh_subtotal: false, realizado: 0, orcado: 0, origem_orcado: "patrimonio", realizado_l: 0, orcado_l: 0 },
    { chave: "TRIBUTOS_IR_CSLL", rotulo: "T", operador: "-", eh_subtotal: false, realizado: 0, orcado: null, origem_orcado: null, realizado_l: 0, orcado_l: null },
    { chave: "RESULTADO_LIQUIDO", rotulo: "Res", operador: "=", eh_subtotal: true, realizado: 14832.12, orcado: 17080, origem_orcado: "orcamento", realizado_l: 0.79, orcado_l: 0.91 },
  ],
};

test("o orçamento é mensal: só meses inteiros", () => {
  assert.equal(periodoDeMesesInteiros(periodoDe("m:2026-02")!), true);
  assert.equal(periodoDeMesesInteiros(periodoDe("s:2025")!), true);
  assert.equal(periodoDeMesesInteiros(periodoDe("l:2026-08-01~2026-09-30")!), true);
  assert.equal(periodoDeMesesInteiros(periodoDe("l:2026-08-02~2026-09-30")!), false);
  assert.equal(periodoDeMesesInteiros(periodoDe("l:2026-08-01~2026-09-29")!), false);
});

test("avaliação pelo tipo e só com orçado (sem plano não há desvio nem cor)", () => {
  assert.deepEqual(avaliar({ grupo: "receita", situacao: "desfavoravel", desvio: -10 }), { texto: "receita abaixo do plano · pior", melhor: false, desvio: -10 });
  assert.equal(avaliar({ grupo: "despesa_operacional", situacao: "favoravel", desvio: -5 }).texto, "gasto abaixo do plano · melhor");
  assert.deepEqual(avaliar({ grupo: "despesa_operacional", situacao: "sem_orcamento", desvio: null }), { texto: "sem orçamento", melhor: null, desvio: null });
});

test("seções por grupo: filhas cobertas logo abaixo do grupo, sem orçamento à parte, total do servidor", () => {
  const s = secoesContas(RESP);
  assert.deepEqual(s.map((x) => x.grupo), ["receita", "despesa_operacional", "fora_do_resultado"]);
  const des = s[1];
  assert.deepEqual(des.orcadas.map((l) => l.codigo_conta_gerencial), ["8", "8.7"]);
  assert.deepEqual(des.semOrcamento.map((l) => l.codigo_conta_gerencial), ["8.12"]);
  assert.equal(des.total.realizado, 3070);
  assert.deepEqual(contasForaDoPlano(RESP).map((l) => l.codigo_conta_gerencial), ["8.12"]);
});

test("desvio por linha da DRE: custo abaixo do plano é melhor; sem orçado fica neutro; depreciação fora", () => {
  const d = desvioPorLinha(RESP);
  // Tributos: sem orçado e sem movimento — fora do gráfico.
  assert.deepEqual(d.map((x) => x.chave), ["RECEITA_VENDAS", "CUSTO_VARIAVEL", "DESPESA_VARIAVEL"]);
  assert.equal(d[0].desvio, -1098.8);
  assert.equal(d[0].melhor, false);
  assert.equal(d[1].melhor, true);
  assert.equal(d[1].texto, "gasto abaixo do plano · melhor");
  assert.equal(d[1].desvioL, -0.065);
  assert.equal(d[2].desvio, null);
  assert.equal(d[2].texto, "sem orçamento");
});

test("frase: receitas e despesas separadas e o resultado contra o plano", () => {
  const f = fraseOrcamento({ periodo: periodoDe("m:2026-09")!, r: RESP, brl: (v) => brl(v, 0), delta: (a, b, bom) => delta(a, b, bom) }).map((t) => t.t).join("");
  assert.match(f, /receitas ficaram R\$\s1\.099 abaixo do orçado e as despesas R\$\s1\.070 acima/);
  assert.match(f, /1 conta teve movimento sem orçamento/);
  assert.match(f, /pior que o plano/);
});

test("DRE com o orçado: linha sem conta orçada e conta fora do orçado ficam sem comparação", () => {
  const cascata: LinhaCascataOrc[] = [
    { chave: "CUSTO_VARIAVEL", rotulo: "", operador: "-", eh_subtotal: false, valor: 20600, contas: [{ codigo: "8.2", nome: "Ração", valor: 20600 }], orcado: true, origem: "orcamento" },
    { chave: "DESPESA_VARIAVEL", rotulo: "", operador: "-", eh_subtotal: false, valor: 0, contas: [], orcado: false, origem: "orcamento" },
    { chave: "EBITDA", rotulo: "", operador: "=", eh_subtotal: true, valor: 9000, contas: [], orcado: true, origem: "orcamento" },
  ];
  const linhas = [
    { chave: "CUSTO_VARIAVEL", subtotal: false, b: -20600, contas: [{ codigo: "8.2", b: -20600 }, { codigo: "8.9", b: 0 }] },
    { chave: "DESPESA_VARIAVEL", subtotal: false, b: 0, contas: [{ codigo: "8.12", b: 0 }] },
    { chave: "EBITDA", subtotal: true, b: 9000, contas: [] },
  ];
  const out = aplicarSemOrcamento(linhas, cascata);
  assert.equal(out[0].b, -20600);
  assert.deepEqual(out[0].contas.map((c) => c.b), [-20600, null]);
  assert.equal(out[1].b, null);
  assert.deepEqual(out[1].contas.map((c) => c.b), [null]);
  assert.equal(out[2].b, 9000);
});

const ITENS = [
  { id: 1, ano: 2026, mes: 1, codigo_conta_gerencial: "8.2", centro_custo: "Leite", tipo: "despesa", valor_orcado: 100 },
  { id: 2, ano: 2026, mes: 2, codigo_conta_gerencial: "8.2", centro_custo: "Leite", tipo: "despesa", valor_orcado: 50 },
  { id: 3, ano: 2026, mes: 2, codigo_conta_gerencial: "8.2", centro_custo: "Leite", tipo: "despesa", valor_orcado: 70 },
  { id: 4, ano: 2026, mes: 1, codigo_conta_gerencial: "8.1", centro_custo: null, tipo: "receita", valor_orcado: 1000 },
];

test("planilha: uma linha por conta e centro; célula com vários itens soma e fica marcada", () => {
  const g = montarGrade(ITENS, new Map([["8.2", "Ração"]]));
  assert.deepEqual(g.map((l) => l.chave), ["8.1|", "8.2|Leite"]);
  assert.equal(g[1].nome, "Ração");
  assert.deepEqual(g[1].valores.slice(0, 3), [100, 120, 0]);
  assert.deepEqual(g[1].itensPorMes.slice(0, 3), [1, 2, 0]);
  const t = totaisGrade(g);
  assert.equal(t.receitas[0], 1000);
  assert.equal(t.despesas[1], 120);
  assert.equal(t.resultado[0], 900);
});

test("planilha: +x%, preencher a linha e copiar o ano anterior não mexem em célula com vários itens", () => {
  const g = montarGrade(ITENS);
  const mais = aplicarPercentual(g, 10);
  assert.deepEqual(mais[1].valores.slice(0, 2), [110, 120]);
  const cheia = preencherLinha(g, "8.2|Leite", 80);
  assert.deepEqual(cheia[1].valores.slice(0, 3), [80, 120, 80]);
  const anterior = montarGrade([{ id: 9, ano: 2025, mes: 3, codigo_conta_gerencial: "8.7", centro_custo: "Leite", tipo: "despesa", valor_orcado: 4000 }]);
  const copia = copiarAnoAnterior(g, anterior, 5);
  assert.deepEqual(copia.map((l) => l.chave), ["8.1|", "8.2|Leite", "8.7|Leite"]);
  assert.equal(copia[2].valores[2], 4200);
});

test("o que salvar: só as células que mudaram, e zerar a linha removida", () => {
  const g = montarGrade(ITENS);
  const nova = preencherLinha(g, "8.2|Leite", 100).filter((l) => l.chave !== "8.1|");
  const cel = celulasAlteradas(g, nova);
  assert.equal(cel.filter((c) => c.codigo_conta_gerencial === "8.2").length, 10); // jan já era 100; fev tem 2 itens
  assert.deepEqual(cel.find((c) => c.codigo_conta_gerencial === "8.1"), { codigo_conta_gerencial: "8.1", centro_custo: null, tipo: "receita", mes: 1, valor: 0 });
  assert.deepEqual(celulasAlteradas(g, g), []);
});

test("valor digitado em pt-BR", () => {
  assert.equal(lerValor("1.234"), 1234);
  assert.equal(lerValor("1.234,5"), 1234.5);
  assert.equal(lerValor("R$ 20.600,00"), 20600);
  assert.equal(lerValor(""), 0);
  assert.equal(lerValor("abc"), null);
  assert.equal(lerValor("12.5"), 12.5);
});
