import { test } from "node:test";
import assert from "node:assert/strict";
import { GRUPOS_RELATORIOS, IDS_RELATORIOS, RELATORIOS_NO_MOLDE, grupoDe, idDoRelatorio } from "./relatoriosNavegacao.ts";

// Os relatórios que existiam na aba antiga (RELATORIOS + Custos + Planejamento) — nenhum pode sumir.
const ANTIGOS = ["fluxo", "caixa_real", "dre", "rmca", "custos", "compra_venda_animais", "compra_semen", "orcamento", "planejamento_financeiro"];

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
  assert.equal(idDoRelatorio("fluxo"), "fluxo");
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
  assert.deepEqual([...RELATORIOS_NO_MOLDE], ["rel_litro", "rel_dre", "rel_orcamento", "rel_cenarios"]);
  assert.equal(grupoDe("inexistente"), null);
});
