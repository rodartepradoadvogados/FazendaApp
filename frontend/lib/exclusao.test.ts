// Testes dos helpers puros da exclusão (Fase 2, plano F5).
// Roda com `npm test` (runner nativo do Node).
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  destinoEditar, exigeMotivo, exigeConfirmacao, confirmacaoEsperada,
  riscoDe, riscoItem, porqueDe, totaisImp, somarImpacto, agruparPorNota,
  chaveDuplicidade, fraseResumo, type ImpactoExclusao, type LinhaImpacto,
} from "./exclusao.ts";

const lin = (t: string, o: Partial<LinhaImpacto> = {}): LinhaImpacto => ({ titulo: t, consequencia: "x", ...o });
const imp = (o: Partial<ImpactoExclusao> = {}): ImpactoExclusao => ({
  item: { tipo: "x", id: "1", titulo: "x" },
  apagar: [], reverter: [], bloqueia: [], avisos: [], risco: null, porque: [], editar_url: null,
  ...o,
});

test("risco baixo: um registro, sem reversão, sem dinheiro", () => {
  assert.equal(riscoDe([imp({ apagar: [lin("a")] })]), "baixo");
});

test("risco médio por reversão", () => {
  assert.equal(riscoDe([imp({ apagar: [lin("a")], reverter: [lin("r")] })]), "medio");
});

test("risco médio por dinheiro em aberto", () => {
  assert.equal(riscoDe([imp({ apagar: [lin("a", { valor: 100 })] })]), "medio");
});

test("risco médio por 2+ registros", () => {
  assert.equal(riscoDe([imp({ apagar: [lin("a"), lin("b")] })]), "medio");
});

test("risco alto por 10+ registros", () => {
  assert.equal(riscoDe([imp({ apagar: [lin("a", { qtd: 10 })] })]), "alto");
});

test("risco alto forçado pelo servidor (animal)", () => {
  assert.equal(riscoItem(imp({ risco: "alto", porque: ["apaga a ficha"] })), "alto");
});

test("porqueDe elenca dinheiro e reversão", () => {
  const p = porqueDe([imp({ apagar: [lin("a", { valor: 50 })], reverter: [lin("r")] })]);
  assert.ok(p.includes("tem dinheiro em aberto"));
  assert.ok(p.some((x) => x.includes("mexe em outros dados")));
});

test("totaisImp soma qtd e dinheiro", () => {
  const t = totaisImp(imp({ apagar: [lin("a", { qtd: 3 }), lin("b", { valor: 200.5 })], reverter: [lin("r")], avisos: [lin("v")] }));
  assert.deepEqual(t, { n: 4, din: 200.5, rev: 1, av: 1 });
});

test("exigências de confirmação", () => {
  assert.equal(exigeMotivo("baixo", true), false);
  assert.equal(exigeMotivo("medio", true), true);
  assert.equal(exigeMotivo("baixo", false), true); // não-admin sempre
  assert.equal(exigeConfirmacao("baixo"), false);
  assert.equal(exigeConfirmacao("alto"), true);
});

test("confirmacaoEsperada: animal = número, demais = APAGAR", () => {
  assert.equal(confirmacaoEsperada("animal", "1042"), "1042");
  assert.equal(confirmacaoEsperada("parto", "42"), "APAGAR");
});

test("destinoEditar aponta o lugar certo e anexa o número do animal", () => {
  assert.equal(destinoEditar("animal", "1042"), "/rebanho?aba=ficha&numero=1042");
  assert.equal(destinoEditar("financeiro", "1"), "/financeiro");
  assert.equal(destinoEditar("tipo_inexistente", "1"), null);
});

test("somarImpacto agrega vários itens", () => {
  const s = somarImpacto([imp({ apagar: [lin("a", { qtd: 2 })] }), imp({ apagar: [lin("b")], reverter: [lin("r")] })]);
  assert.deepEqual(s, { n: 3, din: 0, rev: 1, av: 0 });
});

test("agruparPorNota junta parcelas pela nota", () => {
  const g = agruparPorNota(
    [{ numero_lancamento: "LC-1", id: "1" }, { numero_lancamento: "LC-1", id: "2" }, { numero_lancamento: "LC-2", id: "3" }],
    "numero_lancamento",
  );
  assert.equal(g["LC-1"].length, 2);
  assert.equal(g["LC-2"].length, 1);
});

test("chaveDuplicidade é estável por tipo+alvo", () => {
  assert.equal(chaveDuplicidade("animal", "100"), "animal:100");
});

test("fraseResumo resume bloques", () => {
  assert.equal(fraseResumo(imp({ bloqueia: [{ titulo: "x", motivo: "y", fazer: "z" }] })), "bloqueado");
  assert.equal(fraseResumo(imp({ apagar: [lin("a")], reverter: [lin("r")] })), "1 apagado(s) · 1 revertido(s)");
});