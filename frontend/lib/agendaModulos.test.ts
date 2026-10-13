import { test } from "node:test";
import assert from "node:assert/strict";
import { categoriasAgendaVisiveis, gruposPainelVisiveis, podeVincularAnimalLote, resumoContasAgenda } from "./agendaModulos.ts";

const CATEGORIAS = ["Reprodutivo", "Sanidade", "Produção", "Gestão/Financeiro", "Atividades"];
const soFinanceiro = (m: string) => ["financeiro", "pedidos"].includes(m);
const completo = () => true;

test("fazenda só-financeiro: evento manual só tem Gestão/Financeiro e Atividades, sem vínculo animal/lote", () => {
  assert.deepEqual(categoriasAgendaVisiveis(CATEGORIAS, soFinanceiro), ["Gestão/Financeiro", "Atividades"]);
  assert.equal(podeVincularAnimalLote(soFinanceiro), false);
});

test("fazenda completa mantém todas as categorias e o vínculo", () => {
  assert.deepEqual(categoriasAgendaVisiveis(CATEGORIAS, completo), CATEGORIAS);
  assert.equal(podeVincularAnimalLote(completo), true);
});

test("Painel: só-financeiro esconde Reprodução, Sanidade e Alertas de estoque, mas mantém o financeiro", () => {
  assert.deepEqual(gruposPainelVisiveis(soFinanceiro), { reproducao: false, sanidade: false, estoque: false, financeiro: true });
  assert.deepEqual(gruposPainelVisiveis(completo), { reproducao: true, sanidade: true, estoque: true, financeiro: true });
});

test("rebanho sem estoque: Reprodução/Sanidade aparecem, estoque não", () => {
  const g = gruposPainelVisiveis((m) => ["rebanho", "reprodutivo", "sanitario", "financeiro"].includes(m));
  assert.equal(g.reproducao, true);
  assert.equal(g.sanidade, true);
  assert.equal(g.estoque, false);
});

test("resumo de contas: saldo = total − pago, sem negativos; lista ausente vira zero", () => {
  assert.deepEqual(resumoContasAgenda([{ valor_total: 100, valor_pago: 30 }, { valor_total: 50 }, { valor_total: 10, valor_pago: 20 }]), { n: 3, saldo: 120 });
  assert.deepEqual(resumoContasAgenda(undefined), { n: 0, saldo: 0 });
  assert.deepEqual(resumoContasAgenda(null), { n: 0, saldo: 0 });
});
