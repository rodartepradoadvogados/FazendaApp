import { test } from "node:test";
import assert from "node:assert/strict";
import { fraseFluxo, linhasFluxo, temMovimento, usaResumoNumerico, type MesFluxo, type RespostaFluxo } from "./relatorioFluxo.ts";
import { brl, delta, periodoDe } from "./relatorioContexto.ts";

const MES = (competencia: string, o: Partial<MesFluxo> = {}): MesFluxo => ({
  competencia, entradas: 1000, saidas: 600, sobra: 400, previsto_entradas: 0, previsto_saidas: 0, sobra_prevista: 400, vencidos: 0,
  quantidade: 3, situacao: "realizado", ...o,
});
const RESP = (meses: MesFluxo[]): RespostaFluxo => {
  const soma = (k: keyof MesFluxo) => meses.reduce((s, m) => s + (m[k] as number), 0);
  return {
    periodo: { inicio: `${meses[0].competencia}-01`, fim: `${meses[meses.length - 1].competencia}-28` }, centro_custo: null, hoje: "2026-10-09", regras_v2: true,
    meses, contas: [], meses_com_movimento: meses.filter((m) => m.quantidade).length, compromissos_sem_vencimento: 0, agendado_no_periodo: 0, avisos: [],
    totais: { entradas: soma("entradas"), saidas: soma("saidas"), sobra: soma("sobra"), previsto_entradas: soma("previsto_entradas"),
      previsto_saidas: soma("previsto_saidas"), sobra_prevista: soma("sobra_prevista"), vencidos: soma("vencidos") },
  };
};

test("menos de 3 meses com movimento: resumo numérico em vez de gráfico", () => {
  assert.equal(usaResumoNumerico(RESP([MES("2026-08"), MES("2026-09")])), true);
  assert.equal(usaResumoNumerico(RESP([MES("2026-07"), MES("2026-08", { quantidade: 0 }), MES("2026-09")])), true);
  assert.equal(usaResumoNumerico(RESP([MES("2026-07"), MES("2026-08"), MES("2026-09")])), false);
  assert.equal(usaResumoNumerico(null), true);
  assert.equal(temMovimento(RESP([MES("2026-09", { entradas: 0, saidas: 0, sobra: 0 })])), false);
});

test("mês a mês: comparação pela posição, ano anterior pelo mês e previsto somado no mês em curso", () => {
  const atual = RESP([MES("2026-08"), MES("2026-09"), MES("2026-10", { situacao: "em_curso", previsto_saidas: 300, sobra_prevista: 100 })]);
  const cmp = RESP([MES("2026-05", { sobra: 50, sobra_prevista: 50 }), MES("2026-06"), MES("2026-07")]);
  const ant = RESP([MES("2025-08", { sobra: -20, sobra_prevista: -20 }), MES("2025-09", { quantidade: 0 })]);
  const ls = linhasFluxo(atual, cmp, ant);
  assert.deepEqual(ls.map((l) => [l.competencia, l.sobra, l.cmpCompetencia, l.cmpSobra, l.anoAnterior]), [
    ["2026-08", 400, "2026-05", 50, -20], ["2026-09", 400, "2026-06", 400, null], ["2026-10", 100, "2026-07", 400, null],
  ]);
  assert.equal(ls[2].saidas, 900);
  assert.equal(ls[2].previsto, true);
  assert.equal(linhasFluxo(atual, null, null)[0].cmpSobra, null);
  assert.equal(linhasFluxo(atual, RESP([MES("2026-05", { quantidade: 0, sobra: 0, sobra_prevista: 0 })]), null)[0].cmpSobra, null, "mês sem movimento na comparação: sem dado");
});

test("frase: sobra, comparação e o que ainda está previsto", () => {
  const atual = RESP([MES("2026-09", { situacao: "em_curso", previsto_entradas: 200, previsto_saidas: 500, vencidos: 100 })]);
  const cmp = RESP([MES("2025-09", { sobra: 300 })]);
  const txt = fraseFluxo({ periodo: periodoDe("m:2026-09")!, r: atual, cmp, rotuloCmp: "set/25", brl, delta: (a, b) => delta(a, b) }).map((t) => t.t).join("");
  assert.equal(txt, "Em setembro/2026 entraram R$ 1.000,00 e saíram R$ 600,00 do banco: sobraram R$ 400,00, R$ 100,00 a mais que em set/25. " +
    "Ainda estão previstos R$ 200,00 de entrada e R$ 500,00 de saída até o fim do período, dos quais R$ 100,00 já venceram.");
});
