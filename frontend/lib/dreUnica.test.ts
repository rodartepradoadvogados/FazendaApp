import { test } from "node:test";
import assert from "node:assert/strict";
import { apresentacaoSituacao, kpisDre, regimeDaUrl } from "./dreUnica.ts";

// Cenário da auditoria (março/2031) com tudo ligado — o servidor devolve o
// resumo tirado da cascata. A soma no cliente dava −107.010 (trator, aporte,
// principal e a folha pelo líquido dentro); o resumo dá −4.290.
const resumo = {
  receita_bruta: 10000, receita_liquida: 9850, despesas: 14140, ebitda: -3290, resultado_operacional: -4290,
  resultado_liquido: -4290, margem_liquida_pct: -43.6, fora_da_dre_total: 145680, nao_classificado: 0,
  nao_classificado_receita: 0, nao_classificado_despesa: 0,
};

test("KPIs da DRE usam o resumo do servidor, sem somar no cliente", () => {
  const k = kpisDre({ resumo }, { receitas: 29850, despesas: 136860 });
  assert.deepEqual(k, {
    receita: 9850, despesa: 14140, resultado: -4290, margemPct: -43.6, fonte: "servidor",
    foraDaDre: 145680, naoClassificado: 0,
  });
  assert.equal(k.receita - k.despesa, k.resultado);
});

test("sem resumo (regras antigas) a tela segue com a soma do cliente", () => {
  const k = kpisDre({}, { receitas: 1000, despesas: 250 });
  assert.equal(k.fonte, "cliente");
  assert.equal(k.resultado, 750);
  assert.equal(k.margemPct, 75);
  assert.equal(kpisDre(null, { receitas: 0, despesas: 10 }).margemPct, null);
});

test("um único regime, vindo da URL", () => {
  assert.equal(regimeDaUrl("?regime=caixa"), "caixa");
  assert.equal(regimeDaUrl("?regime=qualquer"), "competencia");
  assert.equal(regimeDaUrl(""), "competencia");
});

test("orçado × realizado: desvio colorido só com orçado", () => {
  assert.equal(apresentacaoSituacao("desfavoravel").cor, "var(--red)");
  assert.equal(apresentacaoSituacao("favoravel").cor, "var(--green-light)");
  assert.equal(apresentacaoSituacao("sem_orcamento").cor, "var(--text-muted)");
  assert.equal(apresentacaoSituacao("fora_do_resultado").rotulo, "Fora do resultado");
  assert.equal(apresentacaoSituacao(undefined).rotulo, "Sem orçamento");
});
