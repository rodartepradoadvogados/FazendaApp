import { test } from "node:test";
import assert from "node:assert/strict";
import { ehBaixaParcial, valorCompetencia, valorRealizado, somaDias, diasAte, perguntaAgendamento, situacaoDe } from "./financeiroSituacao.ts";
import type { Lanc } from "./financeiroTipos.ts";

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
test("pagamento com data futura (regras v2): pede confirmação de agendamento", () => {
  const hoje = "2026-10-08";
  assert.equal(perguntaAgendamento(["2026-10-08"], true, hoje), null);
  assert.equal(perguntaAgendamento(["2026-10-20"], false, hoje), null); // regras antigas: sem pergunta
  assert.match(perguntaAgendamento(["2026-10-20"], true, hoje) ?? "", /^Agendar pagamento para 20\/10\?/);
  assert.match(perguntaAgendamento(["2026-10-20", "2026-10-08", "2026-11-02", "2026-10-20"], true, hoje) ?? "", /20\/10 a 02\/11/);
  assert.equal(perguntaAgendamento([null, undefined, ""], true, hoje), null);
});
test("situação agendada só com data de caixa futura (vinda das regras v2)", () => {
  const base = { tipo: "despesa", valor: 100, valor_pago: 100, desconto_acrescimo: 0, data_pagamento: "2026-10-20", data_vencimento: "2026-10-20" } as unknown as Lanc;
  assert.equal(situacaoDe(base, "2026-10-08").id, "paga");
  const v2 = { ...base, data_caixa: "2026-10-20" } as Lanc;
  assert.deepEqual(situacaoDe(v2, "2026-10-08"), { id: "agendada", classe: "aberto", rotulo: "Agendada para 20/10" });
  assert.equal(situacaoDe(v2, "2026-10-20").id, "paga");
});
