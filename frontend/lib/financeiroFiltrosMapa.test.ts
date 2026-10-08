import { test } from "node:test";
import assert from "node:assert/strict";
import { filtroAntigoParaConsultas } from "./financeiroFiltrosMapa.ts";

test("Contas pagas vira Consultas só de pagamento, mantendo período e filtros", () => {
  const r = filtroAntigoParaConsultas({ campoPeriodoContas: "vencimento", inicio: "2026-09-01", fim: "2026-09-30", centro: "Máquinas", contaBanco: "Sicredi" }, "pagas");
  assert.deepEqual({ m: r.movimento, p: r.periodoPor, d: r.de, a: r.ate, c: r.centro, b: r.banco }, { m: "pagamento", p: "vencimento", d: "2026-09-01", a: "2026-09-30", c: "Máquinas", b: "Sicredi" });
});
test("Extrato respeita o tipo salvo; Livro vira modo livro", () => {
  assert.equal(filtroAntigoParaConsultas({ relTipo: "receita" }, "extrato").movimento, "recebimento");
  assert.equal(filtroAntigoParaConsultas({}, "todas_contas").movimento, "ambos");
  const l = filtroAntigoParaConsultas({ relFornecedor: "Posto Mil" }, "livro");
  assert.equal(l.modo, "livro"); assert.equal(l.fornecedor, "Posto Mil"); assert.equal(l.periodoPor, "pagamento");
});
