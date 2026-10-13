import { test } from "node:test";
import assert from "node:assert/strict";
import {
  marcarModulo, desmarcarModulo, validarSelecao, modulosRemovidos, ordenarPlanos, rotuloPrecoContrato,
  precoDiverge, resumoPreparo, textoRemocao, marcados,
} from "./planosContrato.ts";

const DEPS = {
  estoque: ["rebanho", "financeiro"], pedidos: ["financeiro"], planejamento: ["financeiro"],
  reprodutivo: ["rebanho"], produtivo: ["rebanho"], sanitario: ["rebanho"], alimentacao: ["rebanho"],
};
const BASE = ["rebanho", "financeiro"];

test("marcar estoque marca rebanho e financeiro junto, com explicação", () => {
  const r = marcarModulo({}, "estoque", DEPS);
  assert.deepEqual(marcados(r.proximo).sort(), ["estoque", "financeiro", "rebanho"]);
  assert.equal(r.aviso, "Estoque exige Rebanho e Financeiro — marcamos para você.");
});

test("marcar módulo sem dependência faltando não avisa e preserva o preço já digitado", () => {
  const r = marcarModulo({ financeiro: 50 }, "pedidos", DEPS);
  assert.equal(r.aviso, null);
  assert.equal(r.proximo.financeiro, 50);
  assert.equal(r.proximo.pedidos, 0);
});

test("desmarcar financeiro leva junto pedidos e estoque", () => {
  const sel = { rebanho: 0, financeiro: 0, pedidos: 0, estoque: 0 };
  const r = desmarcarModulo(sel, "financeiro", DEPS, BASE);
  assert.equal(r.bloqueado, false);
  assert.deepEqual(marcados(r.proximo), ["rebanho"]);
  assert.match(r.aviso ?? "", /desmarcamos junto/);
});

test("não deixa tirar o último módulo base", () => {
  const sel = { financeiro: 0, pedidos: 0 };
  const r = desmarcarModulo(sel, "financeiro", DEPS, BASE);
  assert.equal(r.bloqueado, true);
  assert.deepEqual(r.proximo, sel);
});

test("contrato só-financeiro (sem rebanho) é válido; estoque sem rebanho não", () => {
  assert.equal(validarSelecao({ financeiro: 0, pedidos: 0 }, DEPS, BASE), null);
  assert.match(validarSelecao({ financeiro: 0, estoque: 0 }, DEPS, BASE) ?? "", /Estoque exige Rebanho/);
  assert.match(validarSelecao({ consultor: 0 }, DEPS, BASE) ?? "", /precisa de Rebanho e Financeiro/);
  assert.equal(validarSelecao({}, DEPS, BASE), "Marque pelo menos um módulo.");
});

test("módulos removidos e texto do que deixa de aparecer", () => {
  assert.deepEqual(modulosRemovidos(["rebanho", "financeiro", "estoque"], ["financeiro"]), ["rebanho", "estoque"]);
  assert.match(textoRemocao("estoque"), /^Estoque: /);
});

test("planos: ordem fixa com financeiro e desconhecidos no fim", () => {
  assert.deepEqual(ordenarPlanos(["financeiro", "x", "gold", "standard"]), ["standard", "gold", "financeiro", "x"]);
});

test("rótulo de preço fechado x catálogo", () => {
  assert.equal(rotuloPrecoContrato(200, 250), "Preço fechado R$ 200,00 · catálogo hoje R$ 250,00");
  assert.equal(rotuloPrecoContrato(null, null), null);
  assert.equal(precoDiverge(200, 250), true);
  assert.equal(precoDiverge(200, 200), false);
});

test("resumo do preparo do financeiro", () => {
  assert.match(resumoPreparo({ plano_contas_carregado: true, contas_criadas: 12, regras_v2_ligadas: true, ja_preparado: false, mensagens: [] }), /12 contas criadas/);
  assert.match(resumoPreparo({ plano_contas_carregado: false, contas_criadas: 0, regras_v2_ligadas: false, ja_preparado: true, mensagens: [] }), /já estava preparado/);
});
