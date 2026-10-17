import { test } from "node:test";
import assert from "node:assert/strict";
import { colunasPdfDoCard, descreverFiltro, fmtExame, itensDoCard, linhasDoModal, montarExportacao, type EntradaExportacao, type ListaCard } from "./exportAgendaReprodutiva.ts";
import type { ItemCardAgendaReprodutiva } from "./api.ts";
import type { FaseToque } from "./fasesToque.ts";

const item = (n: string, o: Partial<ItemCardAgendaReprodutiva> = {}): ItemCardAgendaReprodutiva => ({
  numero_matriz: n, categoria: "novilha", lote_atual: "13 - Novilhas Novas", estado: "inseminada", del_dias: null, dias_gestacao: null,
  dias_desde_servico: 35, data_servico: "2026-09-12", parto_previsto: null, fase: "a_tocar", ainda_nao: false, dias_para_prazo: null, prazo_tipo: null, ...o,
});

const insem1: ListaCard = { id: "i1", titulo: "Inseminadas 1–29 dias", situacao: "inseminada", itens: [
  item("2341", { ainda_nao: true, dias_para_prazo: 12, prazo_tipo: "toque" }), item("3335", { ainda_nao: true, dias_para_prazo: 3, prazo_tipo: "toque" })] };
const insem30: ListaCard = { id: "i30", titulo: "Inseminadas 30–59 dias", situacao: "inseminada", itens: [
  item("03"), item("460", { fase: "a_reconfirmar", ainda_nao: true, dias_para_prazo: 19, prazo_tipo: "reconfirmacao", diagnostico: "POSITIVO", data_diagnostico: "2026-10-08", retoque: true }), item("075")] };
const pev: ListaCard = { id: "pev", titulo: "PEV", situacao: "pev", itens: [item("88", { estado: "pev", fase: null, dias_desde_servico: null })] };
const vazio: ListaCard = { id: "des", titulo: "A descartar", situacao: "a_descartar", itens: [] };
const outra = { id: "vpd", titulo: "Vazias por diagnóstico", total: 28,
  pdf: { titulo: "Vazias por diagnóstico", colunas: [{ header: "Matriz", key: "numero_matriz" }], linhas: [{ numero_matriz: "1" }] },
  excel: { titulo: "Vazias por diagnóstico", colunas: [{ header: "Matriz", key: "numero_matriz" }], linhas: [{ numero_matriz: "1" }] } };

const base = (o: Partial<EntradaExportacao> = {}): EntradaExportacao => ({
  cards: [pev, insem1, insem30, vazio], outras: [outra], selecionadas: new Set(["pev", "i1", "i30", "des", "vpd"]),
  fases: new Set<FaseToque>(), aplicarFiltro: true, parametros: { dias_toque: 30, dias_reconfirmacao: 30 },
  dataReferencia: "2026-10-17", projetado: false, proximaVisita: "2026-11-04", geradoEm: "17/10/2026", ...o,
});

test("fmtExame: data + letra, ou traço quando não houve", () => {
  assert.equal(fmtExame("2026-10-15", "INDEFINIDO"), "15/10/2026 · I");
  assert.equal(fmtExame("2026-10-08", "POSITIVO"), "08/10/2026 · P");
  assert.equal(fmtExame(null, null), "–");
});

test("itensDoCard: no prazo primeiro e AINDA NÃO do mais perto ao mais longe", () => {
  assert.deepEqual(itensDoCard(insem1, base()).map((i) => i.numero_matriz), ["3335", "2341"]);
  assert.deepEqual(itensDoCard(insem30, base()).map((i) => i.numero_matriz), ["03", "075", "460"]);
});

test("com filtro aplicado só entram as fases escolhidas; sem aplicar, entra tudo", () => {
  const e = base({ fases: new Set<FaseToque>(["a_reconfirmar"]) });
  assert.deepEqual(itensDoCard(insem30, e).map((i) => i.numero_matriz), ["460"]);
  assert.equal(itensDoCard(insem1, e).length, 0);
  assert.equal(itensDoCard(insem30, { ...e, aplicarFiltro: false }).length, 3);
});

test("linhasDoModal: lista vazia e lista sem animais na situação ficam sem poder ser marcadas", () => {
  const sem = linhasDoModal(base());
  assert.equal(sem.find((l) => l.id === "des")!.semAnimais, true);
  assert.equal(sem.find((l) => l.id === "vpd")!.n, 28);
  const com = linhasDoModal(base({ fases: new Set<FaseToque>(["a_tocar"]) }));
  assert.equal(com.find((l) => l.id === "pev")!.semAnimais, true);
  assert.equal(com.find((l) => l.id === "i30")!.n, 2);
  assert.equal(com.find((l) => l.id === "vpd")!.semAnimais, true);
});

test("montarExportacao respeita a seleção e ignora lista vazia", () => {
  const out = montarExportacao(base({ selecionadas: new Set(["i1", "des"]) }));
  assert.deepEqual(out.pdf.secoes.map((s) => s.titulo), ["Inseminadas 1–29 dias — 2 animais"]);
  assert.deepEqual(out.excel.secoes.map((s) => s.titulo), ["Inseminadas 1–29 dias"]);
  assert.equal(out.totais.listas, 1);
  assert.equal(out.totais.animais, 2);
});

test("com o filtro aplicado as 'Outras pendências' ficam de fora (não têm a tocar nem reconfirmar)", () => {
  const out = montarExportacao(base({ fases: new Set<FaseToque>(["a_tocar"]) }));
  assert.ok(!out.pdf.secoes.some((s) => s.titulo.startsWith("Vazias")));
  const sem = montarExportacao(base());
  assert.ok(sem.pdf.secoes.some((s) => s.titulo.startsWith("Vazias")));
});

test("PDF em paisagem, com poucas colunas e largura definida para as de dado curto", () => {
  const out = montarExportacao(base({ selecionadas: new Set(["i30"]) }));
  assert.equal(out.pdf.opcoes.orientacao, "landscape");
  const cols = out.pdf.secoes[0].colunas;
  assert.ok(cols.length <= 10, `colunas demais no PDF: ${cols.length}`);
  assert.deepEqual(cols.map((c) => c.header), ["Matriz", "Categoria", "Lote", "DEL", "Dias da IA", "Toque / confirmação", "Retoque / reconfirmação", "Situação"]);
  const somaFixa = cols.reduce((s, c) => s + (c.larguraPdf ?? 0), 0);
  assert.ok(somaFixa < 269 - 40, "as colunas fixas deixam espaço para o Lote");
  assert.equal(colunasPdfDoCard("pev").length, 4);
  assert.deepEqual(colunasPdfDoCard("gestante").map((c) => c.header).slice(4, 7), ["Dias da IA", "D. gest.", "Parto prev."]);
});

test("a linha AINDA NÃO é destacada e a situação diz quantos dias faltam", () => {
  const out = montarExportacao(base({ selecionadas: new Set(["i30"]) }));
  const s = out.pdf.secoes[0];
  const linha460 = s.linhas.find((l) => l.numero_matriz === "460")!;
  assert.equal(s.destacar!(linha460), true);
  assert.equal(linha460.situacao_fmt, "A reconfirmar · AINDA NÃO, faltam 19 d");
  assert.equal(linha460.toque_fmt, "08/10/2026 · P");
  assert.equal(linha460.retoque_fmt, "–");
  assert.equal(s.destacar!(s.linhas.find((l) => l.numero_matriz === "03")!), false);
});

test("Excel traz todas as colunas e marca as numéricas", () => {
  const out = montarExportacao(base({ selecionadas: new Set(["i30"]) }));
  const cols = out.excel.secoes[0].colunas;
  assert.ok(cols.length > 14);
  assert.ok(cols.find((c) => c.header === "Dias da IA")!.numerico);
  assert.ok(cols.find((c) => c.header === "Dias que faltam")!.numerico);
  assert.equal(out.excel.opcoes.congelarCabecalho, true);
  assert.equal(out.excel.opcoes.autofiltro, true);
});

test("capa: filtro, referência, próxima visita e totais por fase (animais únicos)", () => {
  const out = montarExportacao(base({ selecionadas: new Set(["i1", "i30"]), fases: new Set<FaseToque>(["a_tocar"]), proximaVisita: "2026-11-04" }));
  assert.match(out.pdf.subtitulo, /Data de referência: 17\/10\/2026 \(data atual\)/);
  assert.match(out.pdf.subtitulo, /Filtro: A tocar/);
  assert.match(out.pdf.subtitulo, /Próxima visita reprodutiva: 04\/11\/2026/);
  assert.deepEqual(out.totais.porFase, { a_tocar: 4, a_reconfirmar: 0, reconfirmada: 0 });
  assert.equal(out.totais.aindaNao, 2);
  assert.equal(descreverFiltro(new Set<FaseToque>(), true), "sem filtro (todos os animais das listas)");
  assert.equal(descreverFiltro(new Set<FaseToque>(["a_tocar", "a_reconfirmar"]), true), "A tocar + A reconfirmar");
});

test("a legenda cita os parâmetros da fazenda e nunca o intervalo entre visitas", () => {
  const legenda = montarExportacao(base()).pdf.opcoes.legenda!.join(" ");
  assert.match(legenda, /Dias para toque 30/);
  assert.match(legenda, /Dias para reconfirmação 30/);
  assert.doesNotMatch(legenda, /intervalo/i);
});
