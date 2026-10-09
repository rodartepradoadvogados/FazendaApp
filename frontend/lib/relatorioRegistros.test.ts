import { test } from "node:test";
import assert from "node:assert/strict";
import { buscaGlobal, fraseAnimais, fraseSemen, porqueSemCustoPrenhez, seloNatureza, type Prenhez, type RespostaAnimais, type RespostaSemen } from "./relatorioRegistros.ts";
import { brl, periodoDe } from "./relatorioContexto.ts";

const PREN = (o: Partial<Prenhez> = {}): Prenhez => ({
  preco_dose: { preco: 50, doses: 40, valor: 2000, base: "12_meses" }, inseminacoes: 4, diagnosticadas: 3, aguardando_diagnostico: 1,
  prenhezes: 2, taxa_concepcao_pct: 66.7, custo_semen_usado: 200, custo_semen_diagnosticadas: 150, custo_por_prenhez: 75, ...o,
});

test("busca por número, documento ou GTA olha o histórico inteiro; touro e vendedor não", () => {
  assert.equal(buscaGlobal({ numero: " 950 " }), true);
  assert.equal(buscaGlobal({ documento: "NF-1" }), true);
  assert.equal(buscaGlobal({ touro: "Coors", vendedor: "ABS" }), false);
  assert.equal(buscaGlobal({ numero: "  " }), false);
});

test("selo da natureza: investimento destacado, sem lançamento dito com todas as letras", () => {
  assert.deepEqual(seloNatureza("INVESTIMENTO"), { texto: "investimento", investimento: true });
  assert.deepEqual(seloNatureza("OPERACIONAL"), { texto: "operacional", investimento: false });
  assert.deepEqual(seloNatureza(null), { texto: "sem lançamento", investimento: false });
  assert.equal(seloNatureza("NAO_INFORMADA").texto, "nao informada");
});

test("frase da compra e venda de animais, com o investimento à parte", () => {
  const r = { totais: { vendas: 9000, compras: 25800, saldo: -16800, cab_vendidas: 2, cab_compradas: 3, venda_por_cabeca: 4500, compra_por_cabeca: 8600,
    compras_operacionais: 1800, compras_investimento: 24000, sem_lancamento: 0 } } as RespostaAnimais;
  const txt = fraseAnimais({ periodo: periodoDe("m:2031-03")!, r, brl }).map((t) => t.t).join("");
  assert.equal(txt, "Em março/2031 a fazenda vendeu 2 cabeças por R$ 9.000,00 e comprou 3 cabeças por R$ 25.800,00. " +
    "Destas compras, R$ 24.000,00 são investimento (matriz ou reprodutor para o plantel): ficam fora da DRE e dos custos com as regras novas.");
  const busca = fraseAnimais({ periodo: null, r: { totais: { ...r.totais, compras_investimento: 0, cab_vendidas: 1 } } as RespostaAnimais, brl }).map((t) => t.t).join("");
  assert.match(busca, /^No histórico buscado a fazenda vendeu 1 cabeça/);
});

test("por que não há custo por prenhez (cada caso diz o que falta)", () => {
  assert.equal(porqueSemCustoPrenhez(PREN()), null);
  assert.match(porqueSemCustoPrenhez(PREN({ inseminacoes: 0, custo_por_prenhez: null }))!, /Nenhuma inseminação/);
  assert.match(porqueSemCustoPrenhez(PREN({ diagnosticadas: 0, custo_por_prenhez: null }))!, /4 inseminações ainda sem diagnóstico/);
  assert.match(porqueSemCustoPrenhez(PREN({ prenhezes: 0, custo_por_prenhez: null }))!, /Nenhuma prenhez confirmada/);
  assert.match(porqueSemCustoPrenhez(PREN({ preco_dose: { preco: null, doses: 0, valor: 0, base: null }, custo_por_prenhez: null }))!, /preço da dose/);
  assert.equal(porqueSemCustoPrenhez(null), null);
});

test("frase do sêmen: inseminações, prenhezes, custo por prenhez e as compras", () => {
  const r = { prenhez: PREN(), totais: { gasto: 1000, doses: 20, compras: 1, preco_medio_dose: 50, sem_lancamento: 0 } } as RespostaSemen;
  const per = periodoDe("m:2031-03")!;
  assert.equal(fraseSemen({ periodo: per, r, brl }).map((t) => t.t).join(""),
    "Em março/2031 foram 4 inseminações e 2 prenhezes confirmadas: cada prenhez custou R$ 75,00 só de sêmen. " +
    "1 inseminação aguarda o diagnóstico e fica fora da conta. Foram compradas 20 doses por R$ 1.000,00 (R$ 50,00 por dose).");
  const soCompra = { ...r, prenhez: PREN({ inseminacoes: 0, aguardando_diagnostico: 0 }) } as RespostaSemen;
  assert.equal(fraseSemen({ periodo: per, r: soCompra, brl }).map((t) => t.t).join(""), "Em março/2031 foram compradas 20 doses por R$ 1.000,00 (R$ 50,00 por dose).");
});
