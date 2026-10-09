import { test } from "node:test";
import assert from "node:assert/strict";
import { apresentacaoSituacao } from "./dreUnica.ts";

test("orçado × realizado: desvio colorido só com orçado", () => {
  assert.equal(apresentacaoSituacao("desfavoravel").cor, "var(--red)");
  assert.equal(apresentacaoSituacao("favoravel").cor, "var(--green-light)");
  assert.equal(apresentacaoSituacao("sem_orcamento").cor, "var(--text-muted)");
  assert.equal(apresentacaoSituacao("fora_do_resultado").rotulo, "Fora do resultado");
  assert.equal(apresentacaoSituacao(undefined).rotulo, "Sem orçamento");
});
