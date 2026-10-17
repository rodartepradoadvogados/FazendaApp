import { test } from "node:test";
import assert from "node:assert/strict";
import { d0Retroativo, diaInseminacao, diaSemana, diasDoMolde, fmtData, hojeIso, nomeProtocoloAuto, nosDoCronograma, somaDias } from "./iatfCronograma.ts";

test("dia da inseminação: último dia de hormônio + 2; sem hormônio, D11", () => {
  assert.equal(diaInseminacao([0, 7, 9]), 11);
  assert.equal(diaInseminacao([0, 8, 10, 12]), 14);
  assert.equal(diaInseminacao([]), 11);
});

test("datas em UTC, sem deslizar de dia", () => {
  assert.equal(somaDias("2026-10-17", 11), "2026-10-28");
  assert.equal(somaDias("2026-12-25", 10), "2027-01-04");
  assert.equal(fmtData("2026-10-06"), "06/10/2026");
  assert.equal(fmtData("2026-10-06", true), "06/10");
  assert.equal(fmtData(""), "—");
  assert.equal(diaSemana("2026-10-17"), "sáb");
  assert.equal(hojeIso(new Date(2026, 9, 17, 23, 59)), "2026-10-17");
});

test("nome automático: mesma regra do backend (nomenclatura_protocolo.py)", () => {
  assert.equal(nomeProtocoloAuto("2026-10-06", "Protocolo IATF", 11), "PROTOCOLO IATF - 06/10/26 A 17/10/26 (D0 A D11 - 12 DIAS)");
  assert.equal(nomeProtocoloAuto("2026-10-14", "Curto D0/D8/D10/D12", 14), "CURTO D0/D8/D10/D12 - 14/10/26 A 28/10/26 (D0 A D14 - 15 DIAS)");
  assert.equal(nomeProtocoloAuto("", "x", 11), "");
});

test("cronograma clássico: D0/D7/D9 com os hormônios digitados e a inseminação no D11", () => {
  const nos = nosDoCronograma("2026-10-06", null, [{ dia: 7, produto: "Estron", dose: 2, unidade: "ml" }, { dia: 0, produto: "Cidr", dose: 1, unidade: "unidade" }]);
  assert.deepEqual(nos.map((n) => n.dia), [0, 7, 9, 11]);
  assert.deepEqual(nos[0].linhas, ["1 un Cidr"]);
  assert.deepEqual(nos[1].linhas, ["2 ml Estron"]);
  assert.deepEqual(nos[2].linhas, []);
  assert.equal(nos[3].fim, true);
  assert.equal(nos[3].data, "2026-10-17");
});

test("cronograma de molde com dias livres: a inseminação vem 2 dias depois do último", () => {
  const molde = [{ dia: 0, produto: "Cidr", dose: 1, unidade: "unidade" }, { dia: 8, produto: "Estron", dose: 2, unidade: "ml" }, { dia: 12, produto: "Sincroforte" }];
  const nos = nosDoCronograma("2026-10-14", molde, []);
  assert.deepEqual(nos.map((n) => n.dia), [0, 8, 12, 14]);
  assert.deepEqual(nos[2].linhas, ["Sincroforte"]);
  assert.deepEqual(diasDoMolde(molde), [0, 8, 12]);
});

test("D0 retroativo da IATF avulsa: serviço − 11 dias", () => {
  assert.equal(d0Retroativo("2026-10-17"), "2026-10-06");
});
