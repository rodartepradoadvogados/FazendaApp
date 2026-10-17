import { test } from "node:test";
import assert from "node:assert/strict";
import {
  RESULTADOS_POR_SITUACAO, agruparPorLote, alternarTodasNoPrazo, avisoAindaNao, buscarItens, filtrarPorOrigem, mensagemResultado,
  metodosDisponiveis, pedeMetodo, resumoSelecao, selecaoPadrao, todasNoPrazoMarcadas, type ItemDiagnostico,
} from "./diagnosticoLancamento.ts";

const it = (n: string, lote: string | null, ainda = false, dias: number | null = null): ItemDiagnostico =>
  ({ numero_matriz: n, lote_atual: lote, fase: "a_tocar", ainda_nao: ainda, dias_para_prazo: dias });

test("cada situação oferece só os resultados combinados", () => {
  const nomes = (f: keyof typeof RESULTADOS_POR_SITUACAO) => RESULTADOS_POR_SITUACAO[f].map((r) => r.valor);
  assert.deepEqual(nomes("a_tocar"), ["retoque", "reconfirmada", "negativo", "indefinido"]);
  assert.deepEqual(nomes("a_reconfirmar"), ["reconfirmada", "negativo", "indefinido", "aborto"]);
  assert.deepEqual(nomes("reconfirmada"), ["aborto"]);
});

test("rótulos combinados: 'Positivo — para retoque' e 'Aborto'", () => {
  assert.equal(RESULTADOS_POR_SITUACAO.a_tocar[0].nome, "Positivo — para retoque");
  assert.equal(RESULTADOS_POR_SITUACAO.reconfirmada[0].nome, "Aborto");
});

test("Cio de repasse só com adesivo e só para Negativo", () => {
  assert.deepEqual(metodosDisponiveis(false, "negativo"), ["Palpação", "Ultrassom"]);
  assert.deepEqual(metodosDisponiveis(true, "negativo"), ["Palpação", "Ultrassom", "Cio de repasse"]);
  assert.deepEqual(metodosDisponiveis(true, "retoque"), ["Palpação", "Ultrassom"]);
  assert.deepEqual(metodosDisponiveis(true, ""), ["Palpação", "Ultrassom"]);
});

test("aborto e a tela de reconfirmadas não pedem método", () => {
  assert.equal(pedeMetodo("a_tocar", "retoque"), true);
  assert.equal(pedeMetodo("a_reconfirmar", "aborto"), false);
  assert.equal(pedeMetodo("reconfirmada", "aborto"), false);
});

test("filtrarPorOrigem: animais = todos; lotes e agenda recortam", () => {
  const itens = [it("1", "01 - Alta"), it("2", "13 - Novilhas"), it("3", null)];
  assert.equal(filtrarPorOrigem(itens, "animais", new Set(), new Set()).length, 3);
  assert.deepEqual(filtrarPorOrigem(itens, "lotes", new Set(["13 - Novilhas"]), new Set()).map((i) => i.numero_matriz), ["2"]);
  assert.deepEqual(filtrarPorOrigem(itens, "lotes", new Set(["Sem lote"]), new Set()).map((i) => i.numero_matriz), ["3"]);
  assert.deepEqual(filtrarPorOrigem(itens, "agenda", new Set(), new Set(["1", "3"])).map((i) => i.numero_matriz), ["1", "3"]);
  assert.equal(filtrarPorOrigem(itens, "lotes", new Set(), new Set()).length, 0);
});

test("buscarItens acha por número e por lote, sem acento nem caixa", () => {
  const itens = [it("455", "13 - Novilhas Novas"), it("075", "05 - Secas"), it("9378", "02 - Vacas Média")];
  assert.deepEqual(buscarItens(itens, "45").map((i) => i.numero_matriz), ["455"]);
  assert.deepEqual(buscarItens(itens, "MEDIA").map((i) => i.numero_matriz), ["9378"]);
  assert.deepEqual(buscarItens(itens, "secas").map((i) => i.numero_matriz), ["075"]);
  assert.equal(buscarItens(itens, "  ").length, 3);
});

test("agruparPorLote: lotes em ordem, no prazo antes do AINDA NÃO dentro de cada lote", () => {
  const g = agruparPorLote([
    it("2341", "13 - Novilhas", true, 12), it("464", "13 - Novilhas"), it("075", "05 - Secas"),
    it("467b", "13 - Novilhas", true, 6), it("03", "13 - Novilhas"),
  ]);
  assert.deepEqual(g.map((x) => x.lote), ["05 - Secas", "13 - Novilhas"]);
  assert.deepEqual(g[1].itens.map((i) => i.numero_matriz), ["03", "464", "467b", "2341"]);
});

test("seleção padrão: Animais não marca nada; Lotes e Agenda marcam só quem está no prazo", () => {
  const itens = [it("1", "a"), it("2", "a", true, 5), it("3", "a")];
  assert.equal(selecaoPadrao(itens, "animais", "a_tocar").size, 0);
  assert.deepEqual([...selecaoPadrao(itens, "lotes", "a_tocar")].sort(), ["1", "3"]);
  assert.deepEqual([...selecaoPadrao(itens, "agenda", "a_reconfirmar")].sort(), ["1", "3"]);
});

test("em reconfirmadas nada vem marcado, em nenhuma origem (só aborto, caso a caso)", () => {
  const itens = [it("1", "a"), it("3", "a")];
  for (const o of ["animais", "lotes", "agenda"] as const) assert.equal(selecaoPadrao(itens, o, "reconfirmada").size, 0);
});

test("selecionar todas marca só as no prazo e desmarca só essas", () => {
  const itens = [it("1", "a"), it("2", "a", true, 5), it("3", "a")];
  const marcada = alternarTodasNoPrazo(itens, new Set());
  assert.deepEqual([...marcada].sort(), ["1", "3"]);
  assert.equal(todasNoPrazoMarcadas(itens, marcada), true);
  const comAinda = new Set([...marcada, "2"]);
  assert.deepEqual([...alternarTodasNoPrazo(itens, comAinda)], ["2"]);
});

test("todasNoPrazoMarcadas é falso quando só há AINDA NÃO", () => {
  assert.equal(todasNoPrazoMarcadas([it("1", "a", true, 3)], new Set()), false);
});

test("resumoSelecao conta os AINDA NÃO marcados e o aviso fala no singular e no plural", () => {
  const itens = [it("1", "a"), it("2", "a", true, 5), it("3", "a", true, 9)];
  const r = resumoSelecao(itens, new Set(["1", "2", "3"]));
  assert.equal(r.marcados.length, 3);
  assert.equal(r.ainda, 2);
  assert.match(avisoAindaNao(1), /^1 animal marcado ainda está/);
  assert.match(avisoAindaNao(2), /^2 animais marcados ainda estão/);
  assert.equal(avisoAindaNao(0), "");
});

test("mensagemResultado diz o que salvou e o que falhou", () => {
  assert.deepEqual(mensagemResultado(3, [], "Diagnóstico"), { ok: "Diagnóstico salvo para 3 animais.", erro: null });
  assert.equal(mensagemResultado(1, [], "Diagnóstico").ok, "Diagnóstico salvo para 1 animal.");
  const m = mensagemResultado(2, [{ numero: "9", motivo: "sem prenhez" }], "Diagnóstico");
  assert.equal(m.ok, "Diagnóstico salvo para 2 animais.");
  assert.match(m.erro!, /Não salvou 1 animal: 9 \(sem prenhez\)\./);
  assert.equal(mensagemResultado(0, [{ numero: "9", motivo: "x" }, { numero: "8", motivo: "y" }], "A").ok, null);
});
