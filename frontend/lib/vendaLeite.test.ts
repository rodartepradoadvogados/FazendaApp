import test from "node:test";
import assert from "node:assert/strict";
import { balancoDoMes, emKg, ehUnidade, intervaloDoMes, mesBR, montarPayloadEntrega, ordenarEntregas, textoQtd } from "./vendaLeite.ts";

test("conversão: litro vale 1,029 kg; quilo fica como está; unidade ausente é kg", () => {
  assert.equal(emKg(1000, "kg"), 1000);
  assert.equal(Math.round(emKg(1000, "L") * 1000) / 1000, 1029);
  assert.equal(ehUnidade(undefined), "kg");
  assert.equal(ehUnidade(null), "kg");
  assert.equal(ehUnidade("l"), "L");
  assert.equal(ehUnidade("L"), "L");
});

test("formatação: mês e quantidade", () => {
  assert.equal(mesBR("2026-09"), "09/2026");
  assert.equal(textoQtd(12480, "kg"), "12.480 kg");
  assert.equal(textoQtd(12130.5, "L"), "12.130,5 L");
});

test("intervalo do mês cobre do dia 1 ao último (inclusive fevereiro bissexto)", () => {
  assert.deepEqual(intervaloDoMes("2026-09"), { inicio: "2026-09-01", fim: "2026-09-30" });
  assert.deepEqual(intervaloDoMes("2028-02"), { inicio: "2028-02-01", fim: "2028-02-29" });
  assert.equal(intervaloDoMes("2026-13"), null);
  assert.equal(intervaloDoMes(""), null);
});

test("ordena do mês mais recente para o mais antigo sem mexer na lista original", () => {
  const l = [{ competencia: "2026-03" }, { competencia: "2026-09" }, { competencia: "2026-05" }];
  assert.deepEqual(ordenarEntregas(l).map((x) => x.competencia), ["2026-09", "2026-05", "2026-03"]);
  assert.equal(l[0].competencia, "2026-03");
});

test("payload: exige mês e quantidade > 0; vírgula decimal; nunca grava lixo", () => {
  const ok = montarPayloadEntrega({ competencia: "2026-09", quantidade: "12480,5", unidade: "L", observacao: " soma das notinhas " });
  assert.deepEqual(ok, { dados: { competencia: "2026-09", quantidade_litros: 12480.5, unidade: "L", observacao: "soma das notinhas" } });
  assert.ok("dados" in montarPayloadEntrega({ competencia: "2026-09", quantidade: "100", unidade: "kg", observacao: "" }));
  assert.deepEqual(montarPayloadEntrega({ competencia: "", quantidade: "100", unidade: "kg", observacao: "" }), { erro: "Selecione o mês." });
  assert.deepEqual(montarPayloadEntrega({ competencia: "2026-09", quantidade: "", unidade: "kg", observacao: "" }), { erro: "Informe a quantidade entregue." });
  assert.deepEqual(montarPayloadEntrega({ competencia: "2026-09", quantidade: "0", unidade: "kg", observacao: "" }), { erro: "A quantidade precisa ser um número maior que zero." });
  assert.deepEqual(montarPayloadEntrega({ competencia: "2026-09", quantidade: "abc", unidade: "kg", observacao: "" }), { erro: "A quantidade precisa ser um número maior que zero." });
  const semObs = montarPayloadEntrega({ competencia: "2026-09", quantidade: "5", unidade: "kg", observacao: "  " });
  assert.ok("dados" in semObs && semObs.dados.observacao === undefined);
});

test("balanço: sem dado = null; entregou menos que produziu = positivo; acima = negativo", () => {
  assert.equal(balancoDoMes(null, 13150), null);
  assert.equal(balancoDoMes(12480, null), null);
  const b = balancoDoMes(12480, 13150)!;
  assert.equal(b.dif, 670);
  assert.ok(Math.abs(b.pct - 5.095) < 0.01);
  assert.ok(balancoDoMes(14000, 13150)!.dif < 0);
});
