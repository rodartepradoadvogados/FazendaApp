import { test } from "node:test";
import assert from "node:assert/strict";
import {
  descreverJanela, dividirPorTrato, janelaSobra, opcoesPosicaoLeitura, posicaoValida, tratosIguais, validarTratos,
} from "./tratos.ts";

test("tratos iguais somam 100 com o resto no último", () => {
  assert.deepEqual(tratosIguais(2), [50, 50]);
  assert.deepEqual(tratosIguais(3), [33.33, 33.33, 33.34]);
  assert.deepEqual(tratosIguais(1), [100]);
  assert.equal(validarTratos(tratosIguais(3)), null);
});

test("validação: 1 a 4 tratos, cada um > 0, soma 100", () => {
  assert.match(validarTratos([60, 30])!, /somar 100%/);
  assert.match(validarTratos([20, 20, 20, 20, 20])!, /de 1 a 4/);
  assert.match(validarTratos([100, 0])!, /maior que zero/);
  assert.equal(validarTratos([40, 30, 30]), null);
});

test("opções de posição da leitura", () => {
  assert.deepEqual(opcoesPosicaoLeitura(1), []);
  assert.deepEqual(opcoesPosicaoLeitura(2).map((o) => o.rotulo), ["Trato 1 → Trato 2", "Trato 2 → Trato 1"]);
  assert.deepEqual(opcoesPosicaoLeitura(3).map((o) => o.rotulo), ["Trato 1 → Trato 2", "Trato 2 → Trato 3", "Trato 3 → Trato 1"]);
  assert.equal(posicaoValida(1, null), 1);
  assert.equal(posicaoValida(2, 3), null);
});

test("janela: exemplo do dono (3 tratos, leitura entre T1 e T2)", () => {
  const j = janelaSobra("2026-10-21", 3, 1);
  assert.equal(j.fechamento, "2026-10-21");
  assert.equal(descreverJanela(j.itens), "A sobra se refere aos tratos 2 e 3 do dia 20/10 e ao trato 1 do dia 21/10?");
});

test("janela: leitura antes do 1º trato fecha o dia anterior; 1 trato idem; sem posição = dia civil", () => {
  const j = janelaSobra("2026-11-01", 2, 2);
  assert.equal(j.fechamento, "2026-10-31");
  assert.equal(descreverJanela(j.itens), "A sobra se refere aos tratos 1 e 2 do dia 31/10?");
  assert.equal(descreverJanela(janelaSobra("2026-10-21", 1, 1).itens), "A sobra se refere ao trato 1 do dia 20/10?");
  assert.equal(descreverJanela(janelaSobra("2026-10-21", 2, null).itens), "A sobra se refere aos tratos 1 e 2 do dia 21/10?");
});

test("dividir por trato", () => {
  assert.deepEqual(dividirPorTrato(1000, [40, 30, 30]), [400, 300, 300]);
  assert.deepEqual(dividirPorTrato(null, [50, 50]), [null, null]);
});
