import { test } from "node:test";
import assert from "node:assert/strict";
import {
  contagemChecklist, descreverItem, somaDiferencas, estadoBotaoFechar, fraseConciliacao, fraseFechamento, frasePacote, linhasConciliacao,
  mesDoPeriodo, nomePacote, tituloFechamento,
} from "./relatorioFechamento.ts";
import type { ItemChecklist, SituacaoConciliacao, SituacaoMes } from "./fechamentoApi.ts";

const br = (iso: string) => iso.slice(0, 10).split("-").reverse().join("/");
const brl = (v: number) => `R$ ${v.toFixed(2).replace(".", ",")}`;
const item = (id: string, ok: boolean, bloqueia = true): ItemChecklist => ({
  id, nome: id, txt: "", ok, bloqueia, quantidade: ok ? 0 : 1, itens: ok ? [] : [{}], destino: null, rotulo_acao: null, resumo: null,
});
const mes = (o: Partial<SituacaoMes> = {}): SituacaoMes => ({
  mes: "2026-09", inicio: "2026-09-01", fim: "2026-09-30", regras_v2: true, status: "aberto", pode_fechar_a_partir_de: "2026-10-01",
  evento_atual: null, trilha_do_mes: [], checklist: [item("sem_conta", false), item("folha", true), item("cartao", true)], pendencias: 1,
  retrato_atual: {} as SituacaoMes["retrato_atual"], retrato_atual_sha256: "x", ...o,
});

test("mesDoPeriodo: mês fica; outro tipo vira o último mês fechável do período", () => {
  assert.equal(mesDoPeriodo({ tipo: "m", val: "2026-10", fim: "2026-10-31" }, "2026-10-09"), "2026-10");
  assert.equal(mesDoPeriodo({ tipo: "a", val: "2025", fim: "2025-12-31" }, "2026-10-09"), "2025-12");
  assert.equal(mesDoPeriodo({ tipo: "a", val: "2026", fim: "2026-12-31" }, "2026-10-09"), "2026-09");
  assert.equal(mesDoPeriodo({ tipo: "t", val: "2026-T1", fim: "2026-03-31" }, "2026-01-05"), "2025-12");
});

test("título e frase do fechamento seguem o estado do mês", () => {
  assert.equal(tituloFechamento("2026-09", "aberto"), "Setembro/2026 está pronto para fechar?");
  assert.equal(tituloFechamento("2026-09", "fechado"), "Setembro/2026 está fechado");
  assert.equal(tituloFechamento("2026-10", "em_curso"), "Outubro/2026 ainda está em curso");
  const f = fraseFechamento(mes(), br).map((t) => t.t).join("");
  assert.match(f, /^2 de 3 conferências automáticas estão ok em setembro\/2026\. Resolva/);
  const fechado = mes({ status: "fechado", evento_atual: { id: 1, mes: "2026-09", acao: "fechar", motivo: null, usuario: "Jairo", criado_em: "2026-10-08T17:42:00", retrato_sha256: "a", pendencias_no_fechamento: 0 } });
  assert.match(fraseFechamento(fechado, br).map((t) => t.t).join(""), /fechado em 08\/10\/2026 por Jairo/);
});

test("contagem ignora avisos que não bloqueiam", () => {
  assert.deepEqual(contagemChecklist([item("a", false), item("b", true), item("c", false, false)]), { ok: 1, total: 2, pendentes: 1, avisos: 1 });
});

test("botão Fechar: admin, flag, mês em curso e pendências", () => {
  assert.equal(estadoBotaoFechar(mes(), false, br).mostra, false);
  assert.deepEqual(estadoBotaoFechar(mes({ regras_v2: false }), true, br).habilitado, false);
  assert.match(estadoBotaoFechar(mes({ status: "em_curso" }), true, br).dica, /01\/10\/2026/);
  const p = estadoBotaoFechar(mes(), true, br);
  assert.ok(p.habilitado && p.comPendencias);
  const ok = estadoBotaoFechar(mes({ checklist: [item("a", true)] }), true, br);
  assert.ok(ok.habilitado && !ok.comPendencias);
  assert.equal(estadoBotaoFechar(mes({ status: "fechado" }), true, br).mostra, false);
});

test("descreverItem não mostra nome de funcionário da folha e formata reais", () => {
  assert.deepEqual(descreverItem("folha", { folha_id: 7, valor_liquido: 1500, status: "pendente" }), { titulo: "Folha nº 7", sub: "líquido R$ 1.500,00 · não paga" });
  assert.equal(descreverItem("conciliacao", { conta: "BB", importado: false }).sub, "extrato do mês não importado");
  assert.match(descreverItem("sem_conta", { codigo: "3.1", nome: "Ração", receita: 0, despesa: -10 }).sub, /despesa −R\$ 10,00/);
});

const conc = (o: Partial<SituacaoConciliacao> = {}): SituacaoConciliacao => ({
  conta_corrente_id: 1, conta: "BB", banco: "Banco do Brasil", periodo: { inicio: "2026-09-01", fim: "2026-09-30" }, importado: true,
  linhas: [
    { id: 1, data: "2026-09-05", valor: -100, historico: "PIX", documento: null, status: "pareado", lancamento_id: 9, transferencia_id: null, observacao: null, conciliado_em: null,
      par: { tipo: "lancamento", id: 9, data: "2026-09-05", valor: -100, descricao: "Ração", fornecedor: "Coop", numero_lancamento: "LC-1" }, sugestao: null, alternativas: [] },
    { id: 2, data: "2026-09-01", valor: -68, historico: "TARIFA", documento: null, status: "pendente", lancamento_id: null, transferencia_id: null, observacao: null, conciliado_em: null,
      par: null, sugestao: null, alternativas: [] },
    { id: 3, data: "2026-09-18", valor: -802.2, historico: "JUROS", documento: null, status: "pendente", lancamento_id: null, transferencia_id: null, observacao: null, conciliado_em: null,
      par: null, sugestao: null, alternativas: [{ tipo: "lancamento", id: 4, data: "2026-09-18", valor: -760.1, descricao: "Juros", fornecedor: "BB", numero_lancamento: null, exata: false, diferenca: -42.1 }] },
  ],
  so_no_sistema: [{ tipo: "lancamento", id: 5, data: "2026-09-10", valor: -1250, descricao: "Honorários", fornecedor: "Escritório", numero_lancamento: "LC-5" }],
  contagem: { linhas: 3, pareadas: 1, pendentes: 2, sem_lancamento: 0, so_no_sistema: 1, sugestoes_exatas: 0 },
  movimento: { extrato: -970.2, sistema: -2110.1, diferenca: 1139.9 },
  saldos: { saldo_extrato: 1000, saldo_sistema: 1100, diferenca: -100, bate: false, data: "2026-09-30", pendente_saldo_abertura: false }, ...o,
});

test("linhas da conciliação: o que pede atenção primeiro, sistema junto", () => {
  const l = linhasConciliacao(conc());
  assert.deepEqual(l.map((x) => x.situacao), ["so_extrato", "valor_diferente", "so_sistema", "conciliado"]);
  assert.equal(l[1].sistema, -760.1);
  assert.equal(l[2].extrato, null);
  assert.deepEqual(linhasConciliacao(null), []);
  // −68 + (−802,20 + 760,10) + 0 (par confirmado) + 1.250 (só no sistema) = 1.139,90
  assert.equal(somaDiferencas(l), 1139.9);
});

test("frase da conciliação: bate, não importado, diferença", () => {
  assert.match(fraseConciliacao(conc(), "2026-09", brl).map((t) => t.t).join(""), /diferem em R\$ 100,00\. 2 linhas do extrato precisam de atenção; 1 está conciliada\./);
  assert.match(fraseConciliacao(conc({ importado: false }), "2026-09", brl).map((t) => t.t).join(""), /ainda não foi importado/);
  const bate = conc({ contagem: { linhas: 1, pareadas: 1, pendentes: 0, sem_lancamento: 0, so_no_sistema: 0, sugestoes_exatas: 0 },
    saldos: { saldo_extrato: 1, saldo_sistema: 1, diferenca: 0, bate: true, data: "2026-09-30", pendente_saldo_abertura: false } });
  assert.match(fraseConciliacao(bate, "2026-09", brl).map((t) => t.t).join(""), /batem centavo a centavo/);
});

test("pacote: frase e nome do arquivo", () => {
  const itens = [{ id: "a", nome: "A", formato: "PDF", ok: true, detalhe: "" }, { id: "b", nome: "B", formato: "CSV", ok: false, detalhe: "" }];
  assert.equal(frasePacote(itens, true).map((t) => t.t).join(""), "1 de 2 itens estão prontos para o contador. Como o período ainda não acabou, o pacote é uma prévia. O que falta está marcado e vai junto, no arquivo de pendências.");
  assert.equal(nomePacote("Fazenda Estreito Ponte de Pedra", "2025-01-01", "2025-12-31"), "pacote-contador_fazenda-estreito-ponte-de-pedra_2025-01-01_2025-12-31.zip");
});
