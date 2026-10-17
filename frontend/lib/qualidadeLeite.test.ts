import test from "node:test";
import assert from "node:assert/strict";
import { lerNumero, dataBR, diasEntre, somarDias } from "./producaoGerencial.ts";
import {
  INDICES, classificar, classificarSugerida, descreverFaixasLaticinio, montarPayloadQualidade, ultimaColeta,
  type FaixaBonificacao, type EntradaQualidade,
} from "./qualidadeLeite.ts";

const idx = (c: string) => INDICES.find((i) => i.chave === c)!;
const vazio = { ccs: "", cbt: "", gordura: "", proteina: "", st: "", esd: "", lactose: "", nul: "" };
const base = (o: Partial<EntradaQualidade>): EntradaQualidade => ({ alvo: "tanque", vaca: "", data: "2026-10-17", valores: vazio, observacao: "", ...o });

test("lerNumero: vazio é null, vírgula decimal vale, lixo e negativo viram NaN", () => {
  assert.equal(lerNumero(""), null);
  assert.equal(lerNumero("   "), null);
  assert.equal(lerNumero("3,82"), 3.82);
  assert.equal(lerNumero("312"), 312);
  assert.equal(lerNumero("0"), 0);
  assert.ok(Number.isNaN(lerNumero("abc") as number));
  assert.ok(Number.isNaN(lerNumero("-3") as number));
  assert.ok(Number.isNaN(lerNumero("1,2,3") as number));
});

test("datas: dataBR, diasEntre e somarDias", () => {
  assert.equal(dataBR("2026-10-17"), "17/10/2026");
  assert.equal(dataBR("2026-10-17", true), "17/10");
  assert.equal(dataBR(null), "—");
  assert.equal(diasEntre("2026-10-10", "2026-10-17"), 7);
  assert.equal(somarDias("2026-10-31", 1), "2026-11-01");
});

test("classificação sugerida: na faixa, atenção, fora, inválido, sem valor", () => {
  const ccs = idx("ccs");
  assert.equal(classificarSugerida(ccs, 182)?.situacao, "ok");
  assert.equal(classificarSugerida(ccs, 312)?.situacao, "atencao");
  assert.equal(classificarSugerida(ccs, 548)?.situacao, "fora");
  assert.equal(classificarSugerida(ccs, 548)?.rotulo, "Alto");
  assert.equal(classificarSugerida(ccs, NaN)?.situacao, "invalido");
  assert.equal(classificarSugerida(ccs, null), null);
  assert.equal(classificarSugerida(idx("gordura"), 3.2)?.situacao, "atencao");
  assert.equal(classificarSugerida(idx("gordura"), 2.5)?.rotulo, "Fora da faixa");
});

test("faixas do laticínio mandam; sem faixa que bata, cai na sugerida", () => {
  const faixas: FaixaBonificacao[] = [
    { indicador: "ccs", valor_min: 0, valor_max: 200, ajuste_por_litro: 0.03, ativo: true },
    { indicador: "ccs", valor_min: 200.01, valor_max: 400, ajuste_por_litro: 0, ativo: true },
    { indicador: "ccs", valor_min: 400.01, valor_max: null, ajuste_por_litro: -0.05, ativo: true },
    { indicador: "ccs", valor_min: 0, valor_max: 100, ajuste_por_litro: 9, ativo: false },
  ];
  const ccs = idx("ccs");
  const bonifica = classificar(ccs, 150, faixas)!;
  assert.deepEqual([bonifica.situacao, bonifica.rotulo, bonifica.origem, bonifica.ajuste], ["ok", "Bonifica", "laticinio", 0.03]);
  assert.equal(classificar(ccs, 300, faixas)?.rotulo, "Na faixa");
  const pen = classificar(ccs, 548, faixas)!;
  assert.deepEqual([pen.situacao, pen.rotulo], ["fora", "Penaliza"]);
  // buraco entre 200 e 200,01: nenhuma faixa bate → sugerida
  assert.equal(classificar(ccs, 200.005, faixas)?.origem, "sugerida");
  // índice sem faixa cadastrada → sugerida
  assert.equal(classificar(idx("gordura"), 3.8, faixas)?.origem, "sugerida");
  // sem faixas → sugerida
  assert.equal(classificar(ccs, 150, [])?.origem, "sugerida");
});

test("descreverFaixasLaticinio lista só as ativas do índice, em ordem", () => {
  const faixas: FaixaBonificacao[] = [
    { indicador: "ccs", valor_min: 400, valor_max: null, ajuste_por_litro: -0.05, ativo: true },
    { indicador: "ccs", valor_min: null, valor_max: 200, ajuste_por_litro: 0.03, ativo: true },
    { indicador: "ccs", valor_min: 1, valor_max: 2, ajuste_por_litro: 1, ativo: false },
    { indicador: "cbt", valor_min: 0, valor_max: 50, ajuste_por_litro: 0.01, ativo: true },
  ];
  const t = descreverFaixasLaticinio(faixas, idx("ccs"));
  assert.match(t, /^≤ 200: \+R\$ 0,03\/L · ≥ 400: −R\$ 0,05\/L$/);
  assert.equal(descreverFaixasLaticinio(faixas, idx("nul")), "");
});

test("ultimaColeta: tanque ignora vacas; vaca exige a vaca escolhida", () => {
  const regs = [
    { numero_matriz: null, data_coleta: "2026-10-03", ccs: 100 },
    { numero_matriz: null, data_coleta: "2026-10-10", ccs: 182 },
    { numero_matriz: "11153", data_coleta: "2026-10-15", ccs: 548 },
    { numero_matriz: "11153", data_coleta: "2026-09-26", ccs: 300 },
  ];
  assert.equal(ultimaColeta(regs, "tanque", "")?.ccs, 182);
  assert.equal(ultimaColeta(regs, "vaca", "11153")?.ccs, 548);
  assert.equal(ultimaColeta(regs, "vaca", ""), null);
  assert.equal(ultimaColeta(regs, "vaca", "3335"), null);
});

test("payload: tanque sem índices guarda só a data; vazio nunca vira 0; vírgula decimal", () => {
  const r = montarPayloadQualidade(base({ valores: { ...vazio, ccs: "312", gordura: "3,82" }, observacao: "  laudo  " }));
  assert.ok("dados" in r);
  if ("dados" in r) {
    assert.equal(r.dados.numero_matriz, null);
    assert.equal(r.dados.data_coleta, "2026-10-17");
    assert.equal(r.dados.ccs, 312);
    assert.equal(r.dados.gordura_pct, 3.82);
    assert.equal(r.dados.cbt, null);
    assert.equal(r.dados.nul, null);
    assert.equal(r.dados.observacao, "laudo");
  }
  const so = montarPayloadQualidade(base({}));
  assert.ok("dados" in so && so.dados.ccs === null && so.dados.observacao === undefined);
});

test("payload: uma vaca exige a vaca; sem data não grava; número inválido bloqueia e diz qual", () => {
  assert.deepEqual(montarPayloadQualidade(base({ alvo: "vaca" })), { erro: "Selecione a vaca." });
  assert.deepEqual(montarPayloadQualidade(base({ data: "" })), { erro: "Informe a data da coleta." });
  const ruim = montarPayloadQualidade(base({ valores: { ...vazio, ccs: "abc", proteina: "x" } }));
  assert.ok("erro" in ruim && ruim.erro.includes("CCS") && ruim.erro.includes("Proteína"));
  const vaca = montarPayloadQualidade(base({ alvo: "vaca", vaca: "11153" }));
  assert.ok("dados" in vaca && vaca.dados.numero_matriz === "11153");
});
