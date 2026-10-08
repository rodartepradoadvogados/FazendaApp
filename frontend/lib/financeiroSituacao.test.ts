import { test } from "node:test";
import assert from "node:assert/strict";
import { ehBaixaParcial, valorCompetencia, valorRealizado, somaDias, diasAte } from "./financeiroSituacao.ts";

test("baixa parcial com reparcelamento: realizado e competência não contam o restante duas vezes", () => {
  const p1 = { valor: 1000, valor_pago: 600, desconto_acrescimo: 0 };
  const p2 = { valor: 400, valor_pago: null, desconto_acrescimo: null };
  assert.equal(ehBaixaParcial(p1), true);
  assert.equal(valorRealizado(p1), 600);
  assert.equal(valorCompetencia(p1) + valorCompetencia(p2), 1000);
});
test("desconto não é baixa parcial", () => {
  const l = { valor: 1000, valor_pago: 900, desconto_acrescimo: -100 };
  assert.equal(ehBaixaParcial(l), false);
  assert.equal(valorRealizado(l), 900);
  assert.equal(valorCompetencia(l), 1000);
});
test("datas locais", () => {
  assert.equal(somaDias("2026-10-31", 1), "2026-11-01");
  assert.equal(diasAte("2026-10-10", "2026-10-07"), 3);
});
