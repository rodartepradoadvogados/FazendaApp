// Testes das regras puras da tela "Excluir lançamento" (3 passos). Roda com `npm test` (runner nativo do Node).
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  LIMITE_LOTE, agruparTipos, alternarPagina, alternarSelecao, botoesPagina, casaTipo, chaveRegistro, dataDoRegistro,
  exigencias, fmtContagem, itensDoLote, montarRetorno, nomeCurto, ordenarRegistros, paginar, podarSelecao, proximaOrdem,
  tituloSemData, verboDe, type RegistroBusca, type Selecao, type TipoApi,
} from "./exclusaoTela.ts";

const tipo = (id: string, o: Partial<TipoApi> = {}): TipoApi => ({ id, label: id, sem_filtro_data: false, ...o });
const reg = (id: string, o: Partial<RegistroBusca> = {}): RegistroBusca => ({ id, titulo: `t${id}`, subtitulo: "", ...o });

test("tipos: agrupa por domínio, cadastros à parte e 'Todos' fora da grade", () => {
  const r = agruparTipos([
    tipo("sanidade", { dominio: "san", plural: "sanidades" }),
    tipo("diagnostico", { dominio: "reb", plural: "diagnósticos de gestação" }),
    tipo("parto", { dominio: "reb", plural: "partos" }),
    tipo("lote", { dominio: "cad", cadastro: true, plural: "lotes" }),
    tipo("todos_lancamentos", { dominio: "todos", plural: "lançamentos" }),
  ], "");
  assert.equal(r.todos?.id, "todos_lancamentos");
  assert.deepEqual(r.grupos.map((g) => g.id), ["reb", "san"]);
  assert.deepEqual(r.grupos[0].tipos.map((t) => t.id), ["diagnostico", "parto"]); // ordem da tela, não alfabética
  assert.deepEqual(r.cadastros.map((t) => t.id), ["lote"]);
  assert.equal(r.visiveis, 5);
  assert.equal(r.total, 5);
});

test("tipos: sem dominio (ou dominio desconhecido) cai em 'Outros', nunca some", () => {
  const r = agruparTipos([tipo("novo_x"), tipo("novo_y", { dominio: "zzz" })], "");
  assert.deepEqual(r.grupos.map((g) => [g.id, g.tipos.length]), [["outros", 2]]);
});

test("tipos: busca local por label + plural + dica, sem acento nem caixa", () => {
  const t = tipo("diagnostico", { label: "Diagnóstico de gestação", plural: "diagnósticos", dica: "Desfaz só o exame" });
  assert.equal(casaTipo(t, "DIAGNOSTICO"), true);
  assert.equal(casaTipo(t, "desfaz"), true);
  assert.equal(casaTipo(t, "financeiro"), false);
  const r = agruparTipos([t, tipo("lote", { cadastro: true, plural: "lotes", label: "Lote (cadastro)" })], "lote");
  assert.equal(r.visiveis, 1);
  assert.equal(r.cadastros.length, 1); // a busca que casa com um cadastro o traz (a tela abre o grupo)
  assert.equal(r.grupos.length, 0);
});

test("tipos: nome curto e contagem nula", () => {
  assert.equal(nomeCurto({ label: "Animal (ficha)", plural: "animais" }), "Animais");
  assert.equal(nomeCurto({ label: "Safra (Agricultura)" }), "Safra (Agricultura)");
  assert.equal(fmtContagem(null), "—");
  assert.equal(fmtContagem(undefined), "—");
  assert.equal(fmtContagem(1126), (1126).toLocaleString("pt-BR"));
  assert.equal(fmtContagem(0), "0");
});

test("registros: data vem do servidor; sem ela, da primeira dd/mm/aaaa do título", () => {
  assert.equal(dataDoRegistro(reg("1", { data: "2026-10-17" })), "2026-10-17");
  assert.equal(dataDoRegistro(reg("1", { titulo: "11153 — Toque 17/10/2026" })), "2026-10-17");
  assert.equal(dataDoRegistro(reg("1", { titulo: "Lote 02" })), null);
});

test("registros: título perde a data repetida (ela tem coluna própria)", () => {
  assert.equal(tituloSemData(reg("1", { titulo: "11153 — Toque 17/10/2026", data: "2026-10-17" })), "11153 — Toque");
  assert.equal(tituloSemData(reg("1", { titulo: "NF 55 — 17/10/2026", data: "2026-10-17" })), "NF 55");
  assert.equal(tituloSemData(reg("1", { titulo: "Lote 02" })), "Lote 02");
  assert.equal(tituloSemData(reg("1", { titulo: "17/10/2026", data: "2026-10-17" })), "17/10/2026"); // nunca fica vazio
});

test("registros: ordenar por data (sem data no fim) e por título; sem ordem = a do servidor", () => {
  const a = reg("a", { titulo: "9 x", data: "2026-10-01" });
  const b = reg("b", { titulo: "10 x", data: "2026-10-17" });
  const c = reg("c", { titulo: "11 x" });
  assert.deepEqual(ordenarRegistros([a, b, c], null).map((r) => r.id), ["a", "b", "c"]);
  assert.deepEqual(ordenarRegistros([a, b, c], { coluna: "data", dir: -1 }).map((r) => r.id), ["b", "a", "c"]);
  assert.deepEqual(ordenarRegistros([a, b, c], { coluna: "data", dir: 1 }).map((r) => r.id), ["a", "b", "c"]);
  assert.deepEqual(ordenarRegistros([a, b, c], { coluna: "titulo", dir: 1 }).map((r) => r.id), ["a", "b", "c"]); // numérica: 9 < 10 < 11
});

test("registros: o clique no cabeçalho alterna a direção", () => {
  assert.deepEqual(proximaOrdem(null, "data"), { coluna: "data", dir: -1 });
  assert.deepEqual(proximaOrdem({ coluna: "data", dir: -1 }, "data"), { coluna: "data", dir: 1 });
  assert.deepEqual(proximaOrdem({ coluna: "data", dir: 1 }, "titulo"), { coluna: "titulo", dir: 1 });
});

test("paginação de 50", () => {
  const todas = Array.from({ length: 126 }, (_, i) => i);
  const p1 = paginar(todas, 1, 50);
  assert.deepEqual([p1.de, p1.ate, p1.paginas, p1.linhas.length], [1, 50, 3, 50]);
  const p3 = paginar(todas, 9, 50); // página além do fim volta para a última
  assert.deepEqual([p3.pagina, p3.de, p3.ate], [3, 101, 126]);
  assert.deepEqual([paginar([], 1, 50).de, paginar([], 1, 50).ate], [0, 0]);
  assert.deepEqual(botoesPagina(1, 3), [1, 2, 3]);
  assert.deepEqual(botoesPagina(5, 20), [1, "…", 4, 5, 6, "…", 20]);
  assert.deepEqual(botoesPagina(1, 20), [1, 2, "…", 20]);
});

test("lote: limite de 50 em texto (estourou), não em erro seco", () => {
  let sel: Selecao = new Map();
  for (let i = 0; i < LIMITE_LOTE; i++) sel = alternarSelecao(sel, `diagnostico:${i}`, reg(String(i))).sel;
  assert.equal(sel.size, 50);
  const r = alternarSelecao(sel, "diagnostico:99", reg("99"));
  assert.equal(r.estourou, true);
  assert.equal(r.sel.size, 50);
  assert.equal(alternarSelecao(sel, "diagnostico:0", reg("0")).sel.size, 49); // desmarcar sempre pode
});

test("lote: caixa do cabeçalho marca até o limite e, marcada, desmarca a página", () => {
  const linhas = Array.from({ length: 70 }, (_, i) => reg(String(i)));
  const marcou = alternarPagina(new Map(), linhas, "diagnostico");
  assert.equal(marcou.sel.size, 50);
  assert.equal(marcou.estourou, true);
  const pagina = linhas.slice(0, 50);
  assert.equal(alternarPagina(marcou.sel, pagina, "diagnostico").sel.size, 0);
});

test("lote: itens[] usam o tipo de ORIGEM em 'Todos os lançamentos'", () => {
  const sel: Selecao = new Map([
    ["servico:7", reg("7", { tipo_real: "servico" })],
    ["diagnostico:8:toque", reg("8:toque", { tipo_real: "diagnostico" })],
  ]);
  assert.deepEqual(itensDoLote(sel, "todos_lancamentos"), [
    { tipo: "servico", id: "7" }, { tipo: "diagnostico", id: "8:toque" },
  ]);
  assert.equal(chaveRegistro(reg("8:toque", { tipo_real: "diagnostico" }), "todos_lancamentos"), "diagnostico:8:toque");
  assert.deepEqual(itensDoLote(new Map([["parto:1", reg("1")]]), "parto"), [{ tipo: "parto", id: "1" }]);
});

test("lote: depois de recarregar, só continuam marcados os que ainda estão na lista", () => {
  const sel: Selecao = new Map([["parto:1", reg("1")], ["parto:2", reg("2")]]);
  const novo = podarSelecao(sel, [reg("2"), reg("3")], "parto");
  assert.deepEqual([...novo.keys()], ["parto:2"]);
  assert.equal(podarSelecao(sel, [reg("1"), reg("2")], "parto"), sel); // nada mudou: mesma referência
});

test("verbo: diagnóstico DESFAZ; o resto apaga", () => {
  assert.equal(verboDe("diagnostico"), "desfazer");
  assert.equal(verboDe("financeiro"), "apagar");
});

test("exigências: operador sempre motivo e nunca digita; admin só no médio/alto e digita no alto", () => {
  assert.deepEqual(exigencias("baixo", false), { motivo: true, confirmacao: false });
  assert.deepEqual(exigencias("alto", false), { motivo: true, confirmacao: false });
  assert.deepEqual(exigencias("baixo", true), { motivo: false, confirmacao: false });
  assert.deepEqual(exigencias("medio", true), { motivo: true, confirmacao: false });
  assert.deepEqual(exigencias("alto", true), { motivo: true, confirmacao: true });
});

test("retorno: excluído, lote, pedido, já pedido, apoiado", () => {
  const ok = montarRetorno({ status: "excluido", comprovante: "EX-2026-0007", avisos: ["Estoque devolvido"] }, "toque de 11153");
  assert.deepEqual([ok.tom, ok.comprovante, ok.atalho, ok.detalhes], ["ok", "EX-2026-0007", "trilha", ["Estoque devolvido"]]);
  assert.match(ok.texto, /^Excluído: toque de 11153/);
  const lote = montarRetorno({ status: "excluido", comprovante: "EX-2026-0008", itens: ["a", "b", "c"], bloqueados: [{ titulo: "NF 9", motivo: "x" }] }, "", 4);
  assert.match(lote.texto, /lote de 4 registros/);
  assert.match(lote.detalhes[0], /1 item ficou de fora: NF 9/);
  assert.equal(montarRetorno({ status: "solicitado", id: 5 }, "NF 9").atalho, "pedidos");
  assert.match(montarRetorno({ status: "ja_pedido" }, "NF 9").texto, /já tinha pedido/);
  assert.match(montarRetorno({ status: "apoiado", solicitado_por: "maria" }, "NF 9").texto, /apoiou o pedido de maria/);
  assert.match(montarRetorno({ status: "apoiado" }, "NF 9").texto, /apoiou o pedido que já existia/);
  assert.equal(montarRetorno({ status: "???" }, "x").tom, "erro");
});
