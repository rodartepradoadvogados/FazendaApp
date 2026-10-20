import { test } from "node:test";
import assert from "node:assert/strict";
import {
  diaInseminacaoIatf, hormoniosDoDia, mensagemBaixa, montarMedicamentosBaixa, opcaoEfetiva, origemTemMedicamento,
} from "./baixaProtocolo.ts";
import type { HormonioProtocolo, OpcaoMedicamento } from "./api.ts";

const opcao = (o: Partial<OpcaoMedicamento>): OpcaoMedicamento => ({
  estoque_id: null, nome: "", marca: null, saldo: null, unidade: null, estoque_inicializado: true, sem_estoque: false, ...o,
});

const BE: HormonioProtocolo = {
  produto: "Benzoato de estradiol", dose: 2, unidade: "mL", via: "IM",
  opcoes: [
    opcao({ estoque_id: 10, nome: "Gonadiol", saldo: 50, unidade: "mL", lotes: [
      { id: 101, numero_lote: "A1", data_compra: "2026-08-01", quantidade_restante: 20 },
      { id: 102, numero_lote: "A2", data_compra: "2026-09-01", quantidade_restante: 30 },
    ] }),
    opcao({ estoque_id: 11, nome: "Sincrodiol", saldo: 10, unidade: "mL" }),
  ],
};
const P4: HormonioProtocolo = {
  produto: "Implante de progesterona", dose: 1, unidade: "un", via: "intravaginal",
  opcoes: [opcao({ estoque_id: 20, nome: "Repro One", saldo: 5, unidade: "un" })],
};
const SEM_OPCAO: HormonioProtocolo = { produto: "eCG", dose: 1.5, unidade: "mL", via: "IM", opcoes: [] };

test("só IATF, indução e sanitário perguntam o medicamento", () => {
  assert.equal(origemTemMedicamento("iatf"), true);
  assert.equal(origemTemMedicamento("inducao"), true);
  assert.equal(origemTemMedicamento("sanitario"), true);
  assert.equal(origemTemMedicamento("customizado"), false);
  assert.equal(origemTemMedicamento("lida"), false);
});

test("customizado/lida e dia sem hormônio: não manda `medicamentos` (backend usa os cadastrados)", () => {
  assert.equal(montarMedicamentosBaixa("customizado", [BE]), undefined);
  assert.equal(montarMedicamentosBaixa("lida", [BE]), undefined);
  assert.equal(montarMedicamentosBaixa("iatf", []), undefined);
  const det = { dias: [{ dia: 0, hormonios: [BE] }, { dia: 11 }] } as unknown as Parameters<typeof hormoniosDoDia>[1];
  assert.deepEqual(hormoniosDoDia("iatf", det, 0), [BE]);
  assert.deepEqual(hormoniosDoDia("iatf", det, 11), []);
  assert.deepEqual(hormoniosDoDia("lida", det, 0), []);
  assert.deepEqual(hormoniosDoDia("iatf", det, null), []);
});

test("frasco e lote escolhidos vão no formato do site (produto da opção, estoque_id, lote_id, dose/unidade/via do cadastro)", () => {
  const r = montarMedicamentosBaixa("sanitario", [BE, P4], { 0: 0 }, { 0: 102 });
  assert.deepEqual(r, [
    { produto: "Gonadiol", estoque_id: 10, lote_id: 102, dose: 2, unidade: "mL", via: "IM" },
    // Uma opção só já vem escolhida (mesmo comportamento da Agenda).
    { produto: "Repro One", estoque_id: 20, lote_id: undefined, dose: 1, unidade: "un", via: "intravaginal" },
  ]);
});

test("sem escolha entre várias opções: vai o nome cadastrado, sem estoque_id (backend abate por nome); lote vazio = FIFO", () => {
  const r = montarMedicamentosBaixa("iatf", [BE, SEM_OPCAO], {}, { 0: "" });
  assert.deepEqual(r, [
    { produto: "Benzoato de estradiol", estoque_id: undefined, lote_id: undefined, dose: 2, unidade: "mL", via: "IM" },
    { produto: "eCG", estoque_id: undefined, lote_id: undefined, dose: 1.5, unidade: "mL", via: "IM" },
  ]);
  assert.equal(opcaoEfetiva(BE, undefined), "");
  assert.equal(opcaoEfetiva(P4, undefined), 0);
  assert.equal(opcaoEfetiva(P4, ""), "");
});

test("opção sem frasco em estoque (incluir sem estoque) manda o nome e estoque_id vazio", () => {
  const h: HormonioProtocolo = { ...BE, opcoes: [...BE.opcoes, opcao({ nome: "Estrogin", sem_estoque: true })] };
  const [m] = montarMedicamentosBaixa("inducao", [h], { 0: 2 })!;
  assert.equal(m.produto, "Estrogin");
  assert.equal(m.estoque_id, undefined);
});

test("avisos de estoque da resposta viram a mensagem; sem avisos, 'Baixa registrada.'", () => {
  assert.equal(mensagemBaixa({ avisos: ["Saldo insuficiente de Gonadiol.", "Lote A1 zerado."] }),
    "Saldo insuficiente de Gonadiol. Lote A1 zerado.");
  assert.equal(mensagemBaixa({ avisos: [] }), "Baixa registrada.");
  assert.equal(mensagemBaixa(undefined), "Baixa registrada.");
});

test("dia de inseminação do IATF é o último; demais origens não têm", () => {
  assert.equal(diaInseminacaoIatf("iatf", [{ dia: 0 }, { dia: 8 }, { dia: 10 }, { dia: 11 }]), 11);
  assert.equal(diaInseminacaoIatf("iatf", [{ dia: 0 }]), null);
  assert.equal(diaInseminacaoIatf("sanitario", [{ dia: 0 }, { dia: 7 }]), null);
});
