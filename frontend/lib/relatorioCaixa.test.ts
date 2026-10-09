import { test } from "node:test";
import assert from "node:assert/strict";
import {
  agruparItens, diaSemana, fraseCaixa, lerValorBR, linhaDoTempo, parcelasDa, reservaDe, resumoCaixa, simularCompra, somaMesesDia,
  type DiaCaixa,
} from "./relatorioCaixa.ts";
import { brl } from "./relatorioContexto.ts";
import type { CaixaReal } from "./api.ts";

// 10 dias a partir de 08/10/2026: saldo 10.000; −7.000 no dia 3; +2.000 no dia 6; −6.000 no dia 8.
function serie(): DiaCaixa[] {
  const mov: Record<number, [number, number]> = { 2: [0, 7000], 5: [2000, 0], 7: [0, 6000] };
  let s = 10000;
  return Array.from({ length: 10 }, (_, i) => {
    const [e, sa] = mov[i] ?? [0, 0];
    s += e - sa;
    const dia = `2026-10-${String(8 + i).padStart(2, "0")}`;
    return { data: dia, entradas: e, saidas: sa, saldo: s, itens: e || sa ? [{ descricao: "x", valor: e || sa, tipo: e ? "receita" : "despesa", vencido: false, data_original: dia }] : [] };
  });
}
const CAIXA = (o: Partial<CaixaReal> = {}): CaixaReal => ({
  saldo_inicial: 10000, saldo_final: -1000, total_entradas: 2000, total_saidas: 13000, variacao: -11000, fundo_reserva: 0, folga_minima: -1000,
  dias: 9, primeiro_dia_negativo: "2026-10-15", primeiro_dia_abaixo_da_reserva: null, compromissos_sem_vencimento: 0, contas: [], serie: serie(), ...o,
});

test("valor digitado em reais", () => {
  assert.equal(lerValorBR("24.000,50"), 24000.5);
  assert.equal(lerValorBR("R$ 1.200"), 1200);
  assert.equal(lerValorBR("850.5"), 850.5);
  assert.ok(Number.isNaN(lerValorBR("")));
});

test("datas: mês seguinte limitado ao fim do mês e dia da semana", () => {
  assert.equal(somaMesesDia("2026-01-31", 1), "2026-02-28");
  assert.equal(somaMesesDia("2026-11-15", 2), "2027-01-15");
  assert.equal(diaSemana("2026-10-09"), "sex");
});

test("reserva: o parâmetro manda; sem ele, a sugerida (meses de custeio); sem histórico, nenhuma", () => {
  assert.deepEqual(reservaDe(60000, { sugerido: 90000, meses_folga: 3 }), { valor: 60000, origem: "parametro", meses: 2 });
  assert.deepEqual(reservaDe(0, { sugerido: 90000, meses_folga: 3 }), { valor: 90000, origem: "sugerida", meses: 3 });
  assert.deepEqual(reservaDe(0, { sugerido: 0, meses_folga: 3 }), { valor: 0, origem: "nenhuma", meses: null });
});

test("resumo: menor saldo, 1º negativo, volta e 1º dia abaixo da reserva sugerida", () => {
  const r = resumoCaixa(CAIXA(), reservaDe(0, { sugerido: 5000, meses_folga: 2 }));
  assert.deepEqual(r.menor, { saldo: -1000, data: "2026-10-15" });
  assert.equal(r.primeiroNegativo, "2026-10-15");
  assert.equal(r.voltaPositivo, null);
  assert.equal(r.primeiroAbaixoReserva, "2026-10-10");
  const txt = fraseCaixa(r, reservaDe(0, null), brl, false).map((t) => t.t).join("");
  assert.equal(txt, "O caixa tem R$ 10.000,00 hoje. Nos próximos 9 dias entram R$ 2.000,00 e saem R$ 13.000,00. " +
    "O saldo fica abaixo de zero a partir de 15/10 e não volta dentro da janela; o ponto mais baixo é −R$ 1.000,00 em 15/10.");
});

test("linha do tempo por dia (só com movimento) e por semana (sempre fecha com o saldo)", () => {
  const dias = linhaDoTempo(serie(), "dia");
  assert.deepEqual(dias.map((d) => [d.ini, d.saldoFim]), [["2026-10-10", 3000], ["2026-10-13", 5000], ["2026-10-15", -1000]]);
  const sem = linhaDoTempo(serie(), "semana");
  assert.equal(sem.length, 2);
  assert.deepEqual([sem[0].entradas, sem[0].saidas, sem[0].menorSaldo, sem[0].saldoFim], [2000, 7000, 3000, 5000]);
  assert.equal(sem[1].saldoFim, -1000);
});

test("fatura do cartão numa linha só; vencido e agendado marcados", () => {
  const itens = agruparItens([
    { descricao: "Peça", valor: 500, tipo: "despesa", vencido: false, data_original: "2026-11-15", fatura_cartao: true },
    { descricao: "Ração", valor: 300, tipo: "despesa", vencido: false, data_original: "2026-11-15", fatura_cartao: true },
    { descricao: "Energia", valor: 900, tipo: "despesa", vencido: true, data_original: "2026-10-01" },
    { descricao: "Leite", valor: 9000, tipo: "receita", vencido: false, data_original: "2026-11-15", agendado: true },
  ]);
  assert.deepEqual(itens.map((i) => [i.nome, i.valor]), [["Leite", 9000], ["Energia", 900], ["Fatura do cartão (2 compras)", 800]]);
  assert.deepEqual(itens[0].tags, ["pagamento agendado"]);
  assert.deepEqual(itens[1].tags, ["vencido em 01/10"]);
});

test("Posso comprar? parcelas, novo menor saldo, veredito e sugestão de data", () => {
  assert.deepEqual(parcelasDa({ valor: 1000, data: "2026-10-31", parcelas: 3 }).map((p) => [p.data, p.valor]),
    [["2026-10-31", 333.33], ["2026-11-30", 333.33], ["2026-12-31", 333.34]]);
  const s = serie().slice(0, 7); // até 14/10: menor 3.000, nunca negativo
  const pode = simularCompra(s, { valor: 1000, data: "2026-10-09", parcelas: 1 }, "2026-10-08", 1500);
  assert.ok(pode.ok && pode.veredito === "pode" && pode.menorCom.saldo === 2000);
  const neg = simularCompra(s, { valor: 4000, data: "2026-10-09", parcelas: 1 }, "2026-10-08", 0);
  assert.ok(neg.ok && neg.veredito === "negativo" && neg.primeiroNegativoCom === "2026-10-10");
  // Comprar em 13/10 (depois da entrada de 2.000) não fura nada: 5.000 − 4.000 = 1.000 ≥ 0.
  assert.ok(neg.ok && neg.sugestao === "2026-10-13");
  const reserva = simularCompra(s, { valor: 2000, data: "2026-10-09", parcelas: 1 }, "2026-10-08", 1500);
  assert.ok(reserva.ok && reserva.veredito === "reserva" && reserva.furaReserva);
  assert.deepEqual(simularCompra(s, { valor: 0, data: "2026-10-09", parcelas: 1 }, "2026-10-08", 0), { ok: false, erro: "Informe o valor da compra." });
  assert.equal((simularCompra(s, { valor: 10, data: "2026-10-01", parcelas: 1 }, "2026-10-08", 0) as { erro: string }).erro, "A 1ª parcela precisa ser de hoje em diante.");
  const longe = simularCompra(s, { valor: 300, data: "2026-10-09", parcelas: 3 }, "2026-10-08", 0);
  assert.ok(longe.ok && longe.foraDaJanela === 2);
});
