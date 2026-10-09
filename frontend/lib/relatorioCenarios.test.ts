import { test } from "node:test";
import assert from "node:assert/strict";
import {
  CAMPOS, ajustarMes, calcular, cenariosExemplo, chaveArmazenamento, lerCampo, lerCenarios, mesesProjecao, periodoBaseReal, realDe,
  valoresBase, type FontesReal,
} from "./relatorioCenarios.ts";
import type { IndicadoresLitro } from "./relatorioLitro.ts";

const HOJE = "2026-10-09";
// 3 meses (jul–set/2026 = 92 dias): 56.000 L, receita bruta 140.000, Funrural 2.100, comida 70.000, gente 25.200, outros 9.900.
const LITRO = {
  litros: 56000, receita_leite_bruta: 140000, deducoes_leite: 2100, receita_leite_liquida: 137900,
  comida: 70000, pessoal: 25200, outros_custeio: 9900, coe: 105100,
  preco_liquido_l: 137900 / 56000, coe_l: 105100 / 56000, margem_l: (137900 - 105100) / 56000,
} as unknown as IndicadoresLitro;
const FONTES: FontesReal = {
  ini: "2026-07-01", fim: "2026-09-30", litro: LITRO,
  dreCaixa: {
    cascata: [{ chave: "OUTRAS_REC_DESP", valor: -1920 }],
    fora_da_dre: { grupos: [{ natureza: "FINANCIAMENTO", total: 10500, total_despesa: 10500 }, { natureza: "CAPITAL", total: 18000, total_receita: 0, total_despesa: 18000 }] },
  },
  caixa: { saldo_inicial: 50000, fundo_reserva: 20000 }, vacasLactacao: 30,
};

test("base do Real: os 3 meses fechados antes de hoje; projeção do mês que vem a 12 meses", () => {
  assert.deepEqual(periodoBaseReal(HOJE), { ini: "2026-07-01", fim: "2026-09-30", cod: "l:2026-07-01~2026-09-30" });
  const m = mesesProjecao(HOJE);
  assert.equal(m.length, 12);
  assert.equal(m[0], "2026-11");
  assert.equal(m[11], "2027-10");
});

test("Real vem do servidor: litro, DRE pelo pagamento, Caixa real e Rebanho", () => {
  const r = realDe(FONTES, HOJE);
  assert.equal(r.meses, 3);
  assert.equal(r.v.preco, 137900 / 56000);
  assert.equal(Math.round(r.v.Ldia!), 609); // 56.000 ÷ 92 dias
  assert.equal(r.v.rmca, 0.5);
  assert.equal(r.v.gente, 8400);
  assert.equal(r.v.outros, 3300);
  assert.equal(r.v.parc, (10500 + 1920) / 3);
  assert.equal(r.v.ret, 6000);
  assert.equal(r.v.saldo, 50000);
  assert.equal(r.v.res, 20000);
  assert.equal(r.v.lact, 30);
  assert.equal(r.v.mes, "2027-03");
});

test("com os valores reais o modelo reproduz o COE/L e a sobra/L do servidor", () => {
  const r = realDe(FONTES, HOJE);
  const x = calcular(valoresBase(r, HOJE, true), r, mesesProjecao(HOJE));
  assert.ok(Math.abs(x.coeL! - r.coeL!) < 1e-9);
  assert.ok(Math.abs(x.sobraL! - r.sobraL!) < 1e-9);
  // Sobra do mês = sobra/L × litros do mês; caixa = sobra − parcelas − retirada.
  assert.ok(Math.abs(x.sobraMes - (137900 - 105100) / 3) < 1e-6);
  assert.ok(Math.abs(x.caixaMes - (x.sobraMes - r.v.parc! - 6000)) < 1e-6);
  assert.equal(x.pts.length, 12);
  assert.ok(Math.abs(x.pts[0].s - (50000 + x.caixaMes)) < 0.01);
});

test("compra à vista sai no mês escolhido; menor saldo, meses abaixo da reserva e o primeiro negativo", () => {
  const r = realDe(FONTES, HOJE);
  const v = { ...valoresBase(r, HOJE, true), compra: 80000, mes: "2027-01" };
  const x = calcular(v, r, mesesProjecao(HOJE));
  const sem = calcular({ ...v, compra: 0 }, r, mesesProjecao(HOJE));
  assert.ok(Math.abs(x.pts[2].s - (sem.pts[2].s - 80000)) < 0.01);
  assert.ok(Math.abs(x.pts[1].s - sem.pts[1].s) < 0.01);
  assert.equal(x.negYm, x.pts.find((p) => p.s < 0)?.ym ?? null);
  assert.equal(x.abaixo, x.pts.filter((p) => p.s < 20000).length);
  assert.equal(x.mnS, Math.min(...x.pts.map((p) => p.s)));
});

test("ponto de equilíbrio e campos sem divisor", () => {
  const r = realDe(FONTES, HOJE);
  const v = valoresBase(r, HOJE, true);
  const x = calcular(v, r, mesesProjecao(HOJE));
  const fator = 140000 / 137900;
  const esperado = (8400 + 3300) / (v.preco * (1 - 0.5 * fator)) / r.diasMes;
  assert.ok(Math.abs(x.empate! - esperado) < 1e-9);
  const zero = calcular({ ...v, Ldia: 0, lact: 0, parc: 0 }, r, mesesProjecao(HOJE));
  assert.equal(zero.coeL, null);
  assert.equal(zero.Lvaca, null);
  assert.equal(zero.cob, null);
});

test("sem dados reais o campo fica vazio com o porquê (o dono preenche)", () => {
  const r = realDe({ ...FONTES, litro: null, caixa: null, vacasLactacao: 0, dreCaixa: null }, HOJE);
  assert.equal(r.v.preco, undefined);
  assert.match(r.origem.preco!, /preencha/);
  assert.match(r.origem.saldo!, /administradores/);
  assert.equal(valoresBase(r, HOJE).preco, 0);
});

test("cenários de exemplo, persistência por fazenda e leitura defensiva", () => {
  const base = valoresBase(realDe(FONTES, HOJE), HOJE);
  const cs = cenariosExemplo(base);
  assert.deepEqual(cs.map((c) => c.nome), ["Realista", "Otimista", "Pessimista"]);
  assert.equal(cs[1].v.preco, Math.round((base.preco + 0.12) * 100) / 100);
  assert.equal(chaveArmazenamento(7), "cowdata:cenarios:v1:7");
  assert.notEqual(chaveArmazenamento(7), chaveArmazenamento(8));
  assert.deepEqual(lerCenarios(JSON.stringify(cs)), cs);
  assert.equal(lerCenarios("{"), null);
  assert.equal(lerCenarios(JSON.stringify([{ nome: "x", v: { preco: "a" } }])), null);
  assert.equal(lerCenarios(JSON.stringify([...cs, cs[0]])), null);
  const velho = ajustarMes([{ nome: "A", v: { ...base, mes: "2025-01" } }], mesesProjecao(HOJE));
  assert.equal(velho[0].v.mes, "2027-03");
});

test("valor digitado: decimal com vírgula, milhar com ponto e % em fração", () => {
  const preco = CAMPOS.find((c) => c.k === "preco")!, rmca = CAMPOS.find((c) => c.k === "rmca")!, saldo = CAMPOS.find((c) => c.k === "saldo")!;
  assert.equal(lerCampo("2,65", preco), 2.65);
  assert.equal(lerCampo("54", rmca), 0.54);
  assert.equal(lerCampo("54,5%", rmca), 0.545);
  assert.equal(lerCampo("174.577", saldo), 174577);
  assert.equal(lerCampo("-1.200", saldo), -1200);
  assert.equal(lerCampo("x", saldo), null);
});
