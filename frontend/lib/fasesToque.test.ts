import { test } from "node:test";
import assert from "node:assert/strict";
import { contarPorFase, filtrarPorFases, ordenarNoPrazoPrimeiro, regraDoPrazo, seloBreve, textoFaltam, type ItemComFase } from "./fasesToque.ts";

const it = (n: string, fase: ItemComFase["fase"], ainda = false, dias: number | null = null): ItemComFase =>
  ({ numero_matriz: n, fase, ainda_nao: ainda, dias_para_prazo: dias });

test("contarPorFase conta cada animal uma vez, mesmo em dois cards", () => {
  const c = contarPorFase({
    a: [it("1", "a_tocar"), it("2", "a_tocar"), it("3", "a_reconfirmar")],
    b: [it("2", "a_tocar"), it("4", "reconfirmada")],
    pev: [it("9", null)],
  });
  assert.deepEqual(c, { a_tocar: 2, a_reconfirmar: 1, reconfirmada: 1 });
});

test("filtrarPorFases: vazio devolve tudo; com fase escolhida some quem não tem fase", () => {
  const itens = [it("1", "a_tocar"), it("2", "a_reconfirmar"), it("3", null), it("4", "reconfirmada")];
  assert.equal(filtrarPorFases(itens, new Set()).length, 4);
  assert.deepEqual(filtrarPorFases(itens, new Set(["a_tocar"])).map((x) => x.numero_matriz), ["1"]);
  assert.deepEqual(filtrarPorFases(itens, new Set(["a_tocar", "reconfirmada"])).map((x) => x.numero_matriz), ["1", "4"]);
});

test("ordenarNoPrazoPrimeiro põe os AINDA NÃO no fim, do mais perto para o mais longe", () => {
  const ord = ordenarNoPrazoPrimeiro([it("a", "a_tocar", true, 12), it("b", "a_tocar"), it("c", "a_tocar", true, 3), it("d", "a_tocar")]);
  assert.deepEqual(ord.map((x) => x.numero_matriz), ["b", "d", "c", "a"]);
});

test("ordenarNoPrazoPrimeiro não altera o array recebido", () => {
  const entrada = [it("a", "a_tocar", true, 5), it("b", "a_tocar")];
  ordenarNoPrazoPrimeiro(entrada);
  assert.deepEqual(entrada.map((x) => x.numero_matriz), ["a", "b"]);
});

test("textoFaltam e seloBreve", () => {
  assert.equal(textoFaltam(12), "faltam 12 d");
  assert.equal(textoFaltam(null), "");
  assert.equal(seloBreve(3), true);
  assert.equal(seloBreve(4), false);
  assert.equal(seloBreve(null), false);
});

test("regraDoPrazo cita os parâmetros da fazenda, sem o intervalo entre visitas", () => {
  const t = regraDoPrazo({ dias_toque: 30, dias_reconfirmacao: 35 });
  assert.match(t, /Dias para toque 30/);
  assert.match(t, /Dias para reconfirmação 35/);
  assert.doesNotMatch(t, /visita/i);
});
