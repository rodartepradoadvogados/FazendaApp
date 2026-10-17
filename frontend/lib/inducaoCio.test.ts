import { test } from "node:test";
import assert from "node:assert/strict";
import { estatisticasInducao, estoqueDepois, janelaCio, montarInducao, ultimaInducaoPorMatriz } from "./inducaoCio.ts";

const base = { numeros: ["11153", "3335"], dataAplicacao: "2026-10-17", produto: "Cloprostenol", dose: "", unidade: "ml", via: "", responsavel: "", observacao: "" };

test("cio esperado em 2 a 5 dias depois da aplicação", () => {
  assert.deepEqual(janelaCio("2026-10-17"), { de: "2026-10-19", ate: "2026-10-22" });
  assert.equal(janelaCio(""), null);
});

test("payload: unidade só vai junto da dose; campos vazios não vão", () => {
  const r = montarInducao(base);
  assert.ok("payload" in r);
  if ("payload" in r) {
    assert.equal(r.payload.dose, undefined);
    assert.equal(r.payload.unidade, undefined);
    assert.equal(r.payload.via, undefined);
    assert.deepEqual(r.payload.numeros_matriz, ["11153", "3335"]);
  }
  const comDose = montarInducao({ ...base, dose: "2", unidade: "ml", via: "Intramuscular", responsavel: "Anderson", observacao: "fim do PEV" });
  assert.ok("payload" in comDose);
  if ("payload" in comDose) {
    assert.equal(comDose.payload.dose, 2);
    assert.equal(comDose.payload.unidade, "ml");
    assert.equal(comDose.payload.via, "Intramuscular");
    assert.equal(comDose.payload.observacao, "fim do PEV");
  }
});

test("validações com as mesmas mensagens de sempre", () => {
  assert.deepEqual(montarInducao({ ...base, numeros: [] }), { erro: "Selecione ao menos uma matriz." });
  assert.deepEqual(montarInducao({ ...base, dataAplicacao: "" }), { erro: "Informe a data da aplicação." });
  assert.deepEqual(montarInducao({ ...base, produto: " " }), { erro: "Informe o produto (ex.: Cloprostenol / PGF2α)." });
});

const hist = [
  { id: 1, numero_matriz: "11153", data_aplicacao: "2026-10-15" },
  { id: 2, numero_matriz: "11153", data_aplicacao: "2026-09-01" },
  { id: 3, numero_matriz: "3335", data_aplicacao: "2026-10-01" },
  { id: 4, numero_matriz: "075", data_aplicacao: "2026-08-01" },
  { id: 5, numero_matriz: "9378", data_aplicacao: null },
];

test("última indução por matriz e números da faixa", () => {
  const m = ultimaInducaoPorMatriz(hist);
  assert.equal(m.get("11153"), "2026-10-15");
  assert.equal(m.get("9378"), undefined);
  assert.deepEqual(estatisticasInducao(hist, "2026-10-17"), { observando: 1, ultimos30: 2 });
});

test("estoque depois da baixa: dose × nº de matrizes", () => {
  const est = [{ nome: "Cloprostenol", quantidade: 10, unidade: "ml" }];
  assert.deepEqual(estoqueDepois(est, "Cloprostenol", "2", 3), { atual: 10, depois: 4, unidade: "ml", total: 6 });
  assert.equal(estoqueDepois(est, "Cloprostenol", "", 3), null);
  assert.equal(estoqueDepois(est, "Outro", "2", 3), null);
  assert.equal(estoqueDepois(est, "Cloprostenol", "2", 6)?.depois, -2);
});
