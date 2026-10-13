import { test } from "node:test";
import assert from "node:assert/strict";
import {
  GRUPOS_RELATORIOS, IDS_RELATORIOS, REDIRECIONAMENTOS, RELATORIOS_NO_MOLDE, VISAO_DO_ID_ANTIGO, grupoDe, idDoRelatorio,
  avisoFonteNaoContratada, primeiroRelatorioVisivel, relatorioDisponivel, relatoriosVisiveis, visoesCustosDisponiveis,
} from "./relatoriosNavegacao.ts";

// Os relatórios que existiam na aba antiga (RELATORIOS + Custos + Planejamento) — nenhum pode sumir.
const ANTIGOS = ["fluxo", "caixa_real", "dre", "rmca", "custos", "compra_venda_animais", "compra_semen", "orcamento", "planejamento_financeiro",
  "custo_litro_leite", "custo_vaca_lote", "custo_hectare", "custo_safra"];

test("árvore por pergunta: Painel (entrada), Resultado, Caixa, Leite, Plano, Registros e Entrega ao contador, nessa ordem", () => {
  assert.deepEqual(GRUPOS_RELATORIOS.map((g) => g.label), ["Painel", "Resultado", "Caixa", "Leite", "Plano", "Registros", "Entrega ao contador"]);
  assert.equal(GRUPOS_RELATORIOS[0].itens[0].id, "painel_dono");
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
  // T7: os três nomes antigos do Caixa abrem as telas novas (nenhum sobra apontando para a tela de antes).
  assert.equal(idDoRelatorio("caixa"), "rel_caixa");
  assert.equal(grupoDe("caixa")!.label, "Caixa");
  for (const id of ["caixa", "caixa_real", "fluxo"]) assert.ok(RELATORIOS_NO_MOLDE.has(idDoRelatorio(id)), id);
  // T2: a DRE por conta (tela anterior) saiu; links salvos com ?sub=dre_contas abrem a tela Classificar.
  assert.ok(!IDS_RELATORIOS.has("dre_contas"));
  assert.equal(idDoRelatorio("dre_contas"), "classificar");
  assert.equal(grupoDe("dre_contas")!.label, "Resultado");
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
    "painel_dono", "rel_litro", "rel_dre", "classificar", "rel_caixa", "rel_fluxo", "rel_livro", "custos", "rmca", "reguas_referencia",
    "rel_orcamento", "rel_cenarios", "compra_venda_animais", "compra_semen", "pacote_contador", "fechamento_mes", "conciliacao",
  ]);
  for (const id of RELATORIOS_NO_MOLDE) assert.ok(IDS_RELATORIOS.has(id), id);
  // Fase C1: o grupo Caixa tem as três telas, e o Livro caixa da atividade rural é uma delas.
  assert.deepEqual(GRUPOS_RELATORIOS.find((g) => g.label === "Caixa")!.itens.map((i) => i.id), ["rel_caixa", "rel_fluxo", "rel_livro"]);
  // Fase C4: Réguas moram em Leite (como no mockup); os nomes curtos redirecionam.
  assert.equal(grupoDe("reguas_referencia")!.label, "Leite");
  assert.equal(idDoRelatorio("reguas"), "reguas_referencia");
  assert.equal(idDoRelatorio("painel"), "painel_dono");
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
    ["Painel", ["painel_dono"]],
    ["Resultado", ["rel_litro", "rel_dre", "classificar"]],
    ["Caixa", ["rel_caixa", "rel_fluxo", "rel_livro"]],
    ["Leite", ["custos", "rmca", "reguas_referencia"]],
    ["Plano", ["rel_orcamento", "rel_cenarios", "orcamento_itens", "planejamento_financeiro"]],
    ["Registros", ["compra_venda_animais", "compra_semen"]],
    ["Entrega ao contador", ["pacote_contador", "fechamento_mes", "conciliacao"]],
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

test("Fase C5: pacote, fechamento e conciliação no grupo Entrega ao contador", () => {
  for (const id of ["pacote_contador", "fechamento_mes", "conciliacao"]) assert.equal(grupoDe(id)!.id, "rg-contador", id);
});

// ── Plano Financeiro §2.7: visibilidade por contrato ──
const soFinanceiro = (m: string) => ["financeiro", "pedidos"].includes(m);
const completo = () => true;

test("contrato completo: a árvore visível é a árvore inteira", () => {
  assert.deepEqual(relatoriosVisiveis(completo), GRUPOS_RELATORIOS);
  assert.deepEqual(visoesCustosDisponiveis(completo), ["litro", "lote", "ha", "safra"]);
});

test("só-financeiro: Registros e Plano somem; o resto fica; nenhum grupo vazio", () => {
  const grupos = relatoriosVisiveis(soFinanceiro);
  assert.deepEqual(grupos.map((g) => g.label), ["Painel", "Resultado", "Caixa", "Leite", "Entrega ao contador"]);
  for (const g of grupos) assert.ok(g.itens.length > 0, g.label);
  const ids = new Set(grupos.flatMap((g) => g.itens.map((i) => i.id)));
  for (const id of ["compra_venda_animais", "compra_semen", "rel_orcamento", "rel_cenarios", "orcamento_itens", "planejamento_financeiro"]) assert.ok(!ids.has(id), id);
  for (const id of ["painel_dono", "rel_dre", "rel_caixa", "custos", "pacote_contador", "fechamento_mes", "conciliacao"]) assert.ok(ids.has(id), id);
});

test("só-financeiro: Custos do leite fica só com a visão por litro", () => {
  assert.deepEqual(visoesCustosDisponiveis(soFinanceiro), ["litro"]);
  // Com rebanho mas sem agricultura: lote sim, hectare/safra não.
  assert.deepEqual(visoesCustosDisponiveis((m) => ["financeiro", "rebanho"].includes(m)), ["litro", "lote"]);
});

test("ids antigos seguem o destino: o link salvo ?sub=orcamento é checado como rel_orcamento", () => {
  assert.equal(relatorioDisponivel("orcamento", soFinanceiro), false);
  assert.equal(relatorioDisponivel("rel_orcamento", (m) => m === "planejamento"), true);
  assert.equal(relatorioDisponivel("dre", soFinanceiro), true);
});

test("fonte não contratada: texto claro e sem número; relatório liberado devolve null", () => {
  const msg = avisoFonteNaoContratada("compra_venda_animais", soFinanceiro)!;
  assert.match(msg, /Fonte não contratada/);
  assert.match(msg, /Rebanho/);
  assert.doesNotMatch(msg, /R\$/);
  assert.match(avisoFonteNaoContratada("rel_cenarios", soFinanceiro)!, /Planejamento/);
  assert.equal(avisoFonteNaoContratada("rel_dre", soFinanceiro), null);
});

test("todo item visível para só-financeiro está liberado e o primeiro destino existe", () => {
  for (const g of relatoriosVisiveis(soFinanceiro)) for (const i of g.itens) assert.equal(avisoFonteNaoContratada(i.id, soFinanceiro), null, i.id);
  assert.equal(primeiroRelatorioVisivel(soFinanceiro), "painel_dono");
});
