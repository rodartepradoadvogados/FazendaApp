import { test } from "node:test";
import assert from "node:assert/strict";
import { decisoesDoMes, frasePainel, mesesDoOrcamento, respostaCaixa, respostaOrcado, somaDias, type CaixaLite, type Fmt } from "./painelDono.ts";
import type { IndicadoresLitro } from "./relatorioLitro.ts";
import { IDS_RELATORIOS, REDIRECIONAMENTOS } from "./relatoriosNavegacao.ts";

const fmt: Fmt = { brl: (v) => `R$ ${v.toFixed(2)}`, brl0: (v) => `R$ ${Math.round(v)}`, dia: (iso) => `${iso.slice(8)}/${iso.slice(5, 7)}` };
const texto = (t: { t: string }[]) => t.map((x) => x.t).join("");

const CAIXA: CaixaLite = {
  saldo_inicial: 10000, fundo_reserva: 6000, primeiro_dia_negativo: "2026-10-20", primeiro_dia_abaixo_da_reserva: "2026-10-12",
  serie: [
    { data: "2026-10-09", saldo: 9000, itens: [{ descricao: "Ração", valor: 1000, tipo: "despesa", vencido: true, data_original: "2026-10-01" }] },
    { data: "2026-10-12", saldo: 5000, itens: [{ descricao: "Energia", valor: 4000, tipo: "despesa", vencido: false, data_original: "2026-10-12" }] },
    { data: "2026-10-15", saldo: 8000, itens: [{ descricao: "Leite", valor: 3000, tipo: "receita", vencido: false, data_original: "2026-10-15" }] },
    { data: "2026-10-20", saldo: -500, itens: [{ descricao: "Parcela", valor: 8500, tipo: "despesa", vencido: false, data_original: "2026-10-20" }] },
  ],
};

test("caixa: saldo de hoje, ponto mais baixo e marcos vêm do próprio Caixa real; 7 dias só com saídas", () => {
  const r = respostaCaixa(CAIXA, "2026-10-09")!;
  assert.equal(r.saldoHoje, 10000);
  assert.deepEqual(r.menor, { saldo: -500, data: "2026-10-20" });
  assert.equal(r.negativoEm, "2026-10-20");
  assert.equal(r.abaixoReservaEm, "2026-10-12");
  assert.deepEqual(r.vence7.itens.map((i) => i.descricao), ["Ração", "Energia"]);
  assert.equal(r.vence7.total, 5000);
  assert.equal(r.vence7.temVencida, true);
  assert.equal(respostaCaixa(null, "2026-10-09"), null);
  assert.equal(somaDias("2026-12-28", 7), "2027-01-04");
});

test("orçado: só despesa operacional (totais separados das regras novas); regras antigas e vários anos travam com o porquê", () => {
  assert.deepEqual(mesesDoOrcamento("2026-07-01", "2026-09-30"), { ano: 2026, mes_inicio: 7, mes_fim: 9 });
  assert.equal(mesesDoOrcamento("2025-07-01", "2026-06-30"), null);
  assert.deepEqual(respostaOrcado(null, false), { estado: "varios_anos" });
  assert.deepEqual(respostaOrcado({ total_orcado: 100, total_realizado: 90 }, true), { estado: "regras_antigas" });
  const v2 = (orcado: number, realizado: number, desvio: number | null) => ({ regras_v2: true, total_orcado: orcado, total_realizado: realizado,
    totais: { despesa_operacional: { orcado, realizado, desvio, desvio_pct: orcado ? Math.round(1000 * (desvio ?? 0) / orcado) / 10 : null } } });
  assert.deepEqual(respostaOrcado(v2(0, 500, null), true), { estado: "sem_orcamento", realizado: 500 });
  assert.deepEqual(respostaOrcado(v2(1000, 1200, 200), true), { estado: "ok", orcado: 1000, realizado: 1200, desvio: 200, desvioPct: 20, acima: true });
  const abaixo = respostaOrcado(v2(1000, 900, -100), true)!;
  assert.ok(abaixo.estado === "ok" && !abaixo.acima);
});

const LITRO = { litros: 1000, preco_liquido_l: 2.46, coe_l: 2.0, margem_l: 0.46 } as IndicadoresLitro;

test("frase do painel usa os números do servidor e diz quando o caixa aperta", () => {
  const c = respostaCaixa(CAIXA, "2026-10-09");
  const f = texto(frasePainel({ periodoLabel: "setembro/2026", resultado: 29415, litro: LITRO, caixa: c, fmt }));
  assert.equal(f, "Em setembro/2026 a fazenda teve resultado de R$ 29415. Cada litro foi vendido por R$ 2.46 e custou R$ 2.00 de custeio: sobraram R$ 0.46 por litro. O caixa tem R$ 10000 hoje e fica abaixo de zero em 20/10.");
  const neg = texto(frasePainel({ periodoLabel: "março/2026", resultado: -100, litro: null, caixa: null, fmt }));
  assert.equal(neg, "Em março/2026 a fazenda teve prejuízo de R$ 100.");
});

test("decisões do mês: só o que pede ação, cada uma com o relatório do detalhe", () => {
  const c = respostaCaixa(CAIXA, "2026-10-09");
  const d = decisoesDoMes({ caixa: c, litro: { ...LITRO, margem_l: -0.1 }, naoClassificado: 250, pendenciasNatureza: 1,
    orcado: { estado: "ok", orcado: 1000, realizado: 1200, desvio: 200, desvioPct: 20, acima: true }, fmt });
  assert.deepEqual(d.map((x) => [x.chave, x.relatorio]), [["caixa", "rel_caixa"], ["vence7", "rel_caixa"], ["litro", "rel_litro"], ["orcado", "rel_orcamento"], ["contador", "dre_contas"]]);
  // Integração da Fase C: cada decisão abre um item da árvore, nunca um id antigo que só redireciona.
  for (const x of d) { assert.ok(IDS_RELATORIOS.has(x.relatorio), x.relatorio); assert.ok(!(x.relatorio in REDIRECIONAMENTOS), x.relatorio); }
  assert.match(d[0].titulo, /abaixo da reserva em 12\/10 e fica abaixo de zero em 20\/10/);
  assert.match(d[1].texto, /conta vencida/);
  assert.deepEqual(decisoesDoMes({ caixa: null, litro: LITRO, naoClassificado: 0, pendenciasNatureza: 0, orcado: null, fmt }), []);
});
