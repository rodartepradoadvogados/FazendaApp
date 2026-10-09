import { test } from "node:test";
import assert from "node:assert/strict";
import { GRUPOS_RELATORIOS, IDS_RELATORIOS, REDIRECIONAMENTOS, RELATORIOS_NO_MOLDE, VISAO_DO_ID_ANTIGO, grupoDe, idDoRelatorio } from "./relatoriosNavegacao.ts";

// Os relatórios que existiam na aba antiga (RELATORIOS + Custos + Planejamento) — nenhum pode sumir.
const ANTIGOS = ["fluxo", "caixa_real", "dre", "rmca", "custos", "compra_venda_animais", "compra_semen", "orcamento", "planejamento_financeiro",
  "custo_litro_leite", "custo_vaca_lote", "custo_hectare", "custo_safra"];

test("árvore por pergunta: Resultado, Caixa, Leite, Plano e Registros, nessa ordem", () => {
  assert.deepEqual(GRUPOS_RELATORIOS.map((g) => g.label), ["Resultado", "Caixa", "Leite", "Plano", "Registros"]);
  for (const g of GRUPOS_RELATORIOS) assert.ok(g.pergunta.endsWith("?"), g.label);
});

test("nenhum relatório antigo some: cada id antigo cai num relatório da árvore", () => {
  for (const id of ANTIGOS) {
    const alvo = idDoRelatorio(id);
    assert.ok(IDS_RELATORIOS.has(alvo), `${id} → ${alvo}`);
    assert.ok(grupoDe(id), id);
  }
  assert.equal(idDoRelatorio("dre"), "rel_dre");
  assert.equal(grupoDe("dre")!.label, "Resultado");
  assert.equal(idDoRelatorio("fluxo"), "rel_fluxo");
  assert.equal(idDoRelatorio("caixa_real"), "rel_caixa");
  assert.equal(grupoDe("caixa_real")!.label, "Caixa");
  // A DRE por conta (tela anterior, com a classificação) continua acessível.
  assert.ok(IDS_RELATORIOS.has("dre_contas"));
  // Fase C: Plano › Orçamento no molde; as telas anteriores do orçamento e dos cenários continuam.
  assert.equal(idDoRelatorio("orcamento"), "rel_orcamento");
  assert.equal(grupoDe("orcamento")!.label, "Plano");
  assert.equal(idDoRelatorio("planejamento_financeiro"), "planejamento_financeiro");
  for (const id of ["rel_orcamento", "rel_cenarios", "orcamento_itens", "planejamento_financeiro"]) assert.equal(grupoDe(id)!.id, "rg-plano", id);
});

test("ids únicos na árvore (a aba ativa nunca fica ambígua) e telas novas no molde", () => {
  const ids = GRUPOS_RELATORIOS.flatMap((g) => [g.id, ...g.itens.map((i) => i.id)]);
  assert.equal(new Set(ids).size, ids.length);
  assert.deepEqual([...RELATORIOS_NO_MOLDE], [
    "rel_litro", "rel_dre", "rel_caixa", "rel_fluxo", "rel_livro", "custos", "rmca", "rel_orcamento", "rel_cenarios", "compra_venda_animais", "compra_semen",
  ]);
  for (const id of RELATORIOS_NO_MOLDE) assert.ok(IDS_RELATORIOS.has(id), id);
  // Fase C1: o grupo Caixa tem as três telas, e o Livro caixa da atividade rural é uma delas.
  assert.deepEqual(GRUPOS_RELATORIOS.find((g) => g.label === "Caixa")!.itens.map((i) => i.id), ["rel_caixa", "rel_fluxo", "rel_livro"]);
  assert.equal(grupoDe("inexistente"), null);
});

test("Fase C2: Leite e Registros no molde; as quatro telas de custo caem nas visões de Custos do leite", () => {
  for (const id of ["custos", "rmca", "compra_venda_animais", "compra_semen"]) assert.ok(RELATORIOS_NO_MOLDE.has(id), id);
  assert.equal(grupoDe("rmca")!.label, "Leite");
  assert.equal(grupoDe("compra_semen")!.label, "Registros");
  for (const [antigo, visao] of [["custo_litro_leite", "litro"], ["custo_vaca_lote", "lote"], ["custo_hectare", "ha"], ["custo_safra", "safra"]]) {
    assert.equal(idDoRelatorio(antigo), "custos", antigo);
    assert.equal(VISAO_DO_ID_ANTIGO[antigo], visao, antigo);
    assert.equal(grupoDe(antigo)!.label, "Leite", antigo);
  }
});

test("integração da Fase C: árvore coerente — toda tela nova no molde, telas anteriores marcadas, nenhum id em dois lugares", () => {
  const ordem = GRUPOS_RELATORIOS.map((g) => [g.label, g.itens.map((i) => i.id)]);
  assert.deepEqual(ordem, [
    ["Resultado", ["rel_litro", "rel_dre", "dre_contas"]],
    ["Caixa", ["rel_caixa", "rel_fluxo", "rel_livro"]],
    ["Leite", ["custos", "rmca"]],
    ["Plano", ["rel_orcamento", "rel_cenarios", "orcamento_itens", "planejamento_financeiro"]],
    ["Registros", ["compra_venda_animais", "compra_semen"]],
  ]);
  // O que não está no molde é tela anterior (paridade) e diz isso no rótulo.
  for (const g of GRUPOS_RELATORIOS) for (const i of g.itens) {
    if (!RELATORIOS_NO_MOLDE.has(i.id)) assert.match(i.label, /\(tela anterior\)$/, i.id);
  }
  // Um id antigo redirecionado nunca é também um item da árvore (a aba ativa ficaria ambígua),
  // e todo redirecionamento cai num item (sem cadeia).
  for (const [antigo, novo] of Object.entries(REDIRECIONAMENTOS)) {
    assert.ok(!IDS_RELATORIOS.has(antigo), antigo);
    assert.ok(IDS_RELATORIOS.has(novo), `${antigo} → ${novo}`);
  }
  for (const antigo of Object.keys(VISAO_DO_ID_ANTIGO)) assert.equal(REDIRECIONAMENTOS[antigo], "custos", antigo);
});
