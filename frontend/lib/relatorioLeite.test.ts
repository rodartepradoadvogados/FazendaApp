import { test } from "node:test";
import assert from "node:assert/strict";
import {
  barrasPorLote, foraDoCusto, fraseCustos, fraseRmca, linhasCustoLitro, pendenciasEstimativas, reguaVisivel, serieRmca, temPorVaca, temRmca,
  visaoCusto, type EstimativasCusto, type IndicadoresRmca, type RespostaCustosLeite, type RespostaRmcaVaca,
} from "./relatorioLeite.ts";
import type { IndicadoresLitro, RespostaLitro } from "./relatorioLitro.ts";
import { brl, delta, periodoDe } from "./relatorioContexto.ts";

const IND = (o: Partial<IndicadoresLitro> = {}): IndicadoresLitro => ({
  litros: 10000, litros_mes: 10000, meses: 1, receita_leite_bruta: 25000, deducoes_leite: 400, receita_leite_liquida: 24600,
  comida: 12600, pessoal: 3100, outros_custeio: 4300, custo_variavel: 13000, custo_fixo: 8000, coe: 20000, depreciacao: 800, cot: 20800,
  preco_bruto_l: 2.5, preco_liquido_l: 2.46, comida_l: 1.26, pessoal_l: 0.31, outros_l: 0.43, coe_l: 2.0, depreciacao_l: 0.08, cot_l: 2.08,
  margem_l: 0.46, margem_cot_l: 0.38, margem_pct: 18.7, ponto_equilibrio: null,
  receita_liquida_dre: 30000, resultado_liquido_dre: 9000, nao_classificado: 0, ...o,
});
const EST = (o: Partial<EstimativasCusto> = {}): EstimativasCusto => ({
  familia_informada: false, capital_informado: false, familia_mes: 0, taxa_capital_aa: 6, capital: { rebanho: 0, maquinas: 0, terra: 0 },
  capital_total: 0, familia_periodo: 0, retorno_capital_periodo: null, cot: 20800, ct: null,
  familia_l: 0, retorno_capital_l: null, cot_l: 2.08, ct_l: null, ...o,
});
const CUSTOS = (atual = IND(), est = EST(), media = { meses: 12, coe_l: 1.98, cot_l: 2.05, preco_liquido_l: 2.4 }): RespostaCustosLeite => ({
  periodo: { inicio: "2026-09-01", fim: "2026-09-30" }, regime: "competencia", centro_custo: "Pecuária Leiteira", regras_v2: true,
  litro: { periodo: { inicio: "2026-09-01", fim: "2026-09-30" }, regime: "competencia", centro_custo: "Pecuária Leiteira", regras_v2: true,
    configuracao: { contas_leite: [], contas_alimentacao: [], tem_entrega: true }, atual, serie: [], avisos: [] } as RespostaLitro,
  estimativas: est, media_serie: media,
});

test("visão do custo vem da URL e cai em 'por litro' quando desconhecida", () => {
  assert.equal(visaoCusto("ha"), "ha");
  assert.equal(visaoCusto("safra"), "safra");
  assert.equal(visaoCusto("xyz"), "litro");
  assert.equal(visaoCusto(null), "litro");
});

test("do custeio ao custo total: sem parâmetro a linha fica vazia; COE fecha com as partes", () => {
  const ls = linhasCustoLitro(CUSTOS(), null);
  const m = Object.fromEntries(ls.map((l) => [l.chave, l]));
  assert.equal(Math.round((m.comida.a! + m.gente.a! + m.outros.a!) * 100) / 100, m.coe.a);
  assert.equal(m.familia.a, null); // família não informada: vazio, nunca zero
  assert.equal(m.cot.a, 2.08); // = custo total do Resultado por litro
  assert.equal(m.capital.a, null); assert.equal(m.ct.a, null);
  assert.equal(m.comida.dre, "CUSTO_VARIAVEL"); assert.equal(m.familia.parametro, true);
  const com = linhasCustoLitro(CUSTOS(IND(), EST({ familia_informada: true, capital_informado: true, familia_l: 0.2, cot_l: 2.28, retorno_capital_l: 0.15, ct_l: 2.43 })), CUSTOS());
  const n = Object.fromEntries(com.map((l) => [l.chave, l]));
  assert.deepEqual([n.familia.a, n.cot.a, n.capital.a, n.ct.a], [0.2, 2.28, 0.15, 2.43]);
  assert.deepEqual([n.familia.b, n.cot.b, n.ct.b], [null, 2.08, null]);
  // Comparação sem leite: coluna vazia.
  assert.equal(linhasCustoLitro(CUSTOS(), CUSTOS(IND({ litros: 0 })))[0].b, null);
});

test("regras antigas: comida da tela anterior e 'outros' travado (nunca outro número)", () => {
  const antigo = { ...CUSTOS(), regras_v2: false, alimentacao_tela_anterior: { custo_por_litro: 0.7558, custo_total: 7580, litros: 10029 } };
  const m = Object.fromEntries(linhasCustoLitro(antigo, null).map((l) => [l.chave, l]));
  assert.equal(m.comida.a, 0.7558);
  assert.equal(m.outros.a, null);
  assert.match(m.outros.sub!, /travado/);
  assert.equal(m.gente.a, 0.31); assert.equal(m.coe.a, 2.0);
});

test("frase dos custos: custeio, média de 12 meses, variação, COT/CT e preço", () => {
  const per = periodoDe("m:2026-09")!;
  const txt = (r: RespostaCustosLeite, b: RespostaCustosLeite | null, rot: string | null) =>
    fraseCustos({ periodo: per, r, b, rotuloCmp: rot, brl, delta }).map((t) => t.t).join("");
  assert.equal(txt(CUSTOS(), CUSTOS(IND({ coe_l: 2.08 })), "set/25"),
    "Em setembro/2026 o custo de custeio — o que saiu do bolso — foi R$ 2,00 por litro (média de 12 meses: R$ 1,98), R$ 0,08 a menos que em set/25. " +
    "Somando o desgaste dos bens, R$ 2,08. O leite foi vendido por R$ 2,46 líquido.");
  const comCt = txt(CUSTOS(IND(), EST({ familia_informada: true, cot_l: 2.19, ct_l: 2.32, capital_informado: true })), null, null);
  assert.match(comCt, /Somando o desgaste dos bens e a família, R\$ 2,19; com o retorno do capital, R\$ 2,32\./);
  assert.deepEqual(fraseCustos({ periodo: per, r: CUSTOS(IND({ litros: 0 })), b: null, rotuloCmp: null, brl, delta }), []);
});

test("pendências das estimativas e o que ficou fora do custo por natureza", () => {
  assert.deepEqual(pendenciasEstimativas(EST()).map((p) => p.pronto), [false, false]);
  assert.deepEqual(pendenciasEstimativas(null), []);
  const fora = foraDoCusto({ fora_por_natureza: { INVESTIMENTO: 120000, FINANCIAMENTO: 5000, CAPITAL: 0 } });
  assert.deepEqual(fora.map((f) => f.natureza), ["INVESTIMENTO", "FINANCIAMENTO"]);
  assert.match(fora[0].rotulo, /Investimento/);
  assert.deepEqual(foraDoCusto(null), []);
});

test("barras por lote: maior primeiro, com as vacas no rótulo", () => {
  const b = barrasPorLote({
    periodo: { inicio: "", fim: "" }, centro_custo: null, tem_vacas_no_periodo: true, num_vacas: 3, despesas_total: 300, custo_por_vaca: 100,
    por_lote: [{ lote: "02", num_vacas: 1, custo_alocado: 100, custo_por_vaca: 100 }, { lote: "01", num_vacas: 2, custo_alocado: 200, custo_por_vaca: 100 }],
  });
  assert.deepEqual(b.map((x) => [x.nome, x.valor, x.sub]), [["01", 200, "2 vacas"], ["02", 100, "1 vaca"]]);
});

const RM = (o: Partial<IndicadoresRmca> = {}): IndicadoresRmca => ({
  receita_bruta: 60000, receita_liquida: 59100, comida: 23000, rmca: 37000, rmca_liquida: 36100, comida_receita_pct: 38.33,
  comida_receita_liquida_pct: 38.92, receita_vaca_dia: 20, comida_vaca_dia: 7.67, rmca_vaca_dia: 12.33, rmca_liquida_vaca_dia: 12.03,
  litros: 24000, litros_vaca_dia: 8, vaca_dias: 3000, dias: 30, vacas: 100, vacas_media: 100, ...o,
});
const RESP_RMCA = (atual = RM(), serie: (IndicadoresRmca & { competencia: string })[] = []): RespostaRmcaVaca => ({
  periodo: { inicio: "2026-09-01", fim: "2026-09-30" }, regras_v2: true, configurado: true, contas_receita: ["Leite"], contas_custo: ["Ração"],
  meta_rmca: 0, gerencial: { receita_leite: atual.receita_bruta, custo_alimentacao: atual.comida, rmca: atual.rmca },
  atual, fisico: { ...RM({ comida: 25000, rmca_vaca_dia: 11.67 }), itens: [{ ingrediente: "Milho", quantidade: 1, valor_unitario: 1, custo: 1, quantidade_kg: 1, preco_padrao_kg: 1, preco_ultima_compra_kg: null }] },
  preco_medio_litro_leite: null, serie, por_lote: [], preco_bruto_l: 2.5, avisos: [],
});

test("RMCA: há o que mostrar, por vaca só com controle leiteiro", () => {
  assert.equal(temRmca(RESP_RMCA()), true);
  assert.equal(temRmca(RESP_RMCA(RM({ receita_bruta: 0, comida: 0 }))), false);
  assert.equal(temRmca(null), false);
  assert.equal(temPorVaca(RM()), true);
  assert.equal(temPorVaca(RM({ vaca_dias: 0, rmca_vaca_dia: null })), false);
});

test("série do RMCA no mesmo formato do gráfico preço × custo; mês sem vaca fica vazio", () => {
  const s = serieRmca(RESP_RMCA(RM(), [
    { ...RM(), competencia: "2026-08" },
    { ...RM({ receita_vaca_dia: 5, comida_vaca_dia: 7, rmca_vaca_dia: -2 }), competencia: "2026-09" },
    { ...RM({ vaca_dias: 0, rmca_vaca_dia: null, receita_vaca_dia: null, comida_vaca_dia: null }), competencia: "2026-10" },
  ]));
  assert.deepEqual(s[0].faixaPos, [7.67, 20]); assert.equal(s[0].faixaNeg, null);
  assert.deepEqual(s[1].faixaNeg, [5, 7]);
  assert.deepEqual([s[2].preco, s[2].custo, s[2].faixaPos], [null, null, null]);
});

test("frase do RMCA: por vaca/dia com a comparação e o físico; sem controle, o total", () => {
  const per = periodoDe("m:2026-09")!;
  const txt = fraseRmca({ periodo: per, r: RESP_RMCA(), rb: RESP_RMCA(RM({ rmca_vaca_dia: 11.5 })), rotuloCmp: "set/25", brl }).map((t) => t.t).join("");
  assert.equal(txt, "Em setembro/2026 cada vaca em lactação rendeu R$ 20,00 de leite por dia e a comida custou R$ 7,67: sobraram R$ 12,33 por vaca/dia " +
    "para pagar o resto (R$ 11,50 em set/25). Pelo consumo registrado na Alimentação, a sobra seria R$ 11,67.");
  const sem = fraseRmca({ periodo: per, r: RESP_RMCA(RM({ vaca_dias: 0, rmca_vaca_dia: null })), rb: null, rotuloCmp: null, brl }).map((t) => t.t).join("");
  assert.match(sem, /sobraram R\$ 37\.000,00\. Sem Controle leiteiro no período, não dá para dividir por vaca\.$/);
});

test("régua só aparece publicada, com faixa válida, aceite feito e dentro da validade", () => {
  const ok = { vencida: false, publicacao: { liberada: true }, aceite_pendente: false, reguas: [
    { codigo: "comida_receita", nome: "Comida ÷ receita do leite", unidade: "%", situacao: "publicada", exibir_faixa: true,
      faixa: { min: 40, max: 55, eficiente_ate: 45 }, fidedignidade: "media", vence_em: "2027-01-31" },
  ] };
  assert.deepEqual(reguaVisivel(ok, "comida_receita", "2026-10-09"), {
    codigo: "comida_receita", nome: "Comida ÷ receita do leite", min: 40, max: 55, unidade: "%", fidedignidade: "media", venceEm: "2027-01-31",
  });
  const com = (mut: (r: typeof ok) => void) => { const r = structuredClone(ok); mut(r); return reguaVisivel(r, "comida_receita", "2026-10-09"); };
  assert.equal(com((r) => { r.reguas[0].situacao = "em_revisao"; }), null);
  assert.equal(com((r) => { r.reguas[0].exibir_faixa = false; }), null);
  assert.equal(com((r) => { (r.reguas[0] as { faixa: unknown }).faixa = null; }), null);
  assert.equal(com((r) => { r.reguas[0].faixa = { min: 55, max: 40, eficiente_ate: 0 }; }), null);
  assert.equal(com((r) => { r.vencida = true; }), null);
  assert.equal(com((r) => { r.aceite_pendente = true; }), null);
  assert.equal(com((r) => { r.reguas[0].vence_em = "2026-10-01"; }), null);
  assert.equal(reguaVisivel(ok, "outra", "2026-10-09"), null);
  // Endpoint ausente, versão antiga sem "situacao" ou resposta estranha: nada.
  assert.equal(reguaVisivel(null, "comida_receita", "2026-10-09"), null);
  assert.equal(reguaVisivel({ reguas: [{ codigo: "comida_receita", exibir_faixa: true, faixa: { min: 40, max: 55 } }] }, "comida_receita", "2026-10-09"), null);
  assert.equal(reguaVisivel("erro", "comida_receita", "2026-10-09"), null);
});
