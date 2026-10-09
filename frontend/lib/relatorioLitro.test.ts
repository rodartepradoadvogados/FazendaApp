import { test } from "node:test";
import assert from "node:assert/strict";
import { fraseLitro, linhasLitro, pendenciasLitro, serieLitro, temResultadoPorLitro, type IndicadoresLitro, type RespostaLitro } from "./relatorioLitro.ts";
import { brl, delta, periodoDe } from "./relatorioContexto.ts";

const IND = (o: Partial<IndicadoresLitro> = {}): IndicadoresLitro => ({
  litros: 10000, litros_mes: 10000, meses: 1, receita_leite_bruta: 25000, deducoes_leite: 400, receita_leite_liquida: 24600,
  comida: 12600, pessoal: 3100, outros_custeio: 4300, custo_variavel: 13000, custo_fixo: 8000, coe: 20000, depreciacao: 800, cot: 20800,
  preco_bruto_l: 2.5, preco_liquido_l: 2.46, comida_l: 1.26, pessoal_l: 0.31, outros_l: 0.43, coe_l: 2.0, depreciacao_l: 0.08, cot_l: 2.08,
  margem_l: 0.46, margem_cot_l: 0.38, margem_pct: 18.7,
  ponto_equilibrio: { litros_periodo: 6993, litros_mes: 6993, receita_periodo: 17202, folga_pct: 43, contribuicao_por_litro: 1.16 },
  receita_liquida_dre: 30000, resultado_liquido_dre: 9000, nao_classificado: 0, ...o,
});
const RESP = (atual: IndicadoresLitro, serie: (IndicadoresLitro & { competencia: string })[] = []): RespostaLitro => ({
  periodo: { inicio: "2026-09-01", fim: "2026-09-30" }, regime: "competencia", centro_custo: "Pecuária Leiteira", regras_v2: true,
  configuracao: { contas_leite: ["Venda de leite"], contas_alimentacao: [], tem_entrega: true }, atual, serie, avisos: [],
});

test("sem litros ou sem receita do leite não há resultado por litro", () => {
  assert.equal(temResultadoPorLitro(IND()), true);
  assert.equal(temResultadoPorLitro(IND({ litros: 0, preco_liquido_l: null })), false);
  assert.equal(temResultadoPorLitro(IND({ receita_leite_liquida: 0, preco_liquido_l: 0 })), false);
  assert.equal(temResultadoPorLitro(null), false);
});

test("pendências com o caminho de 1 clique, prontas ou não", () => {
  const p = pendenciasLitro(RESP(IND({ litros: 0 })));
  assert.deepEqual(p.map((x) => [x.chave, x.pronto]), [["leite", true], ["comida", false], ["litros", false]]);
  assert.equal(p[2].href, "/lancamentos?sub=entrega_leite");
  assert.deepEqual(pendenciasLitro(null), []);
});

test("linha a linha: do preço bruto à sobra depois de repor; o custeio fecha com as partes", () => {
  const ls = linhasLitro(IND(), IND({ margem_l: 0.42, preco_liquido_l: 2.5 }));
  const m = Object.fromEntries(ls.map((l) => [l.chave, l]));
  assert.equal(m.preco_liquido.a, 2.46); assert.equal(m.preco_liquido.b, 2.5);
  assert.equal(m.deducoes.a, 0.04);
  assert.equal(Math.round((m.comida.a! + m.gente.a! + m.outros.a!) * 100) / 100, m.coe.a);
  assert.equal(m.margem.a, 0.46); assert.equal(m.margem.bom, "sobe"); assert.equal(m.coe.bom, "desce");
  assert.equal(m.gente.dre, "GASTOS_PESSOAL");
  // Comparação sem leite: coluna vazia, nunca zero.
  assert.equal(linhasLitro(IND(), IND({ litros: 0, preco_liquido_l: null }))[0].b, null);
});

test("série de 12 meses: faixa da sobra, faixa da falta e mês sem leite vazio", () => {
  const s = serieLitro(RESP(IND(), [
    { ...IND({ preco_liquido_l: 2.4, coe_l: 2.1 }), competencia: "2026-07" },
    { ...IND({ preco_liquido_l: 2.0, coe_l: 2.2 }), competencia: "2026-08" },
    { ...IND({ litros: 0, preco_liquido_l: null, coe_l: null }), competencia: "2026-09" },
  ]));
  assert.deepEqual(s[0].faixaPos, [2.1, 2.4]); assert.equal(s[0].faixaNeg, null);
  assert.deepEqual(s[1].faixaNeg, [2.0, 2.2]); assert.equal(s[1].faixaPos, null);
  assert.deepEqual([s[2].preco, s[2].custo, s[2].faixaPos], [null, null, null]);
});

test("frase-resumo: preço, custeio, sobra e a maior mudança", () => {
  const per = periodoDe("m:2026-09")!;
  const txt = fraseLitro({
    periodo: per, regime: "comp", a: IND(), b: IND({ margem_l: 0.42, outros_l: 0.49, comida_l: 1.28 }), rotuloCmp: "set/25", brl, delta,
  }).map((t) => t.t).join("");
  assert.equal(txt, "Em setembro/2026 cada litro foi vendido por R$ 2,46 líquido e custou R$ 2,00 de custeio — sobraram R$ 0,46 por litro, " +
    "R$ 0,04 a mais que em set/25. A maior mudança veio de outros custeios (−R$ 0,06 por litro).");
  const falta = fraseLitro({ periodo: per, regime: "comp", a: IND({ margem_l: -0.1 }), b: null, rotuloCmp: null, brl, delta }).map((t) => t.t).join("");
  assert.match(falta, /faltaram R\$ 0,10 por litro\.$/);
});
