import test from "node:test";
import assert from "node:assert/strict";
import {
  alvoDaAcao, doseTotal, filtrarAnimais, interpretarRetornoAplicar, montarPayloadAplicar, ordenarAnimais, preverEstoque,
  reanalisadasMarcadas, segmentosDaAgenda, textoPrevisao, textoRetornoMarcar, type Marcadas, type ParamsAplicacao,
} from "./bstLote.ts";

const HOJE = "2026-10-17";
const agenda = {
  bst_elegiveis: [
    { numero_matriz: "1274", grupo: "02 - Vacas Alta", del_atual: 91, del_projetado: 101, requer_reanalise: false },
    { numero_matriz: "2507", grupo: "01 - Novilhas Alta", del_atual: 76, del_projetado: 86 },
  ],
  bst_nunca_aplicados: [
    { numero_matriz: "1296", grupo: "02 - Vacas Alta", del_atual: 60, del_projetado: 70, requer_reanalise: false },
    { numero_matriz: "3335", grupo: "01 - Novilhas Alta", del_atual: 28, del_projetado: 38, requer_reanalise: true, origem_inducao_lactacao: true, motivo_exclusao: "Indução de lactação — protocolo já aplicou BST" },
    { numero_matriz: "075", grupo: "02 - Vacas Alta", del_atual: 143, del_projetado: 153, requer_reanalise: true, motivo_exclusao: "Excluída manualmente do BST" },
  ],
  bst_excluidos: [
    { numero_matriz: "2574", grupo: "04 - Pós-parto/Tratamento", del_atual: 26, del_projetado: 36, motivo_exclusao: "DEL 36 < 60 dias" },
    { numero_matriz: "9999", grupo: null, del_atual: null, del_projetado: null },
  ],
};
const segs = segmentosDaAgenda(agenda);
const params = (o: Partial<ParamsAplicacao> = {}): ParamsAplicacao => ({ data: HOJE, produto: "Lactotropin", dose: "", unidade: "unidade", porAnimal: true, resp: "", ...o });
const estoque = [{ nome: "Lactotropin", unidade: "unidade", quantidade: 50 }, { nome: "Boostin", unidade: "dose", quantidade: 20 }];

test("segmentos: lê as três listas da agenda, com reanálise, indução e motivo", () => {
  assert.deepEqual([segs.aptas.length, segs.incluir.length, segs.inaptas.length], [2, 3, 2]);
  assert.equal(segs.incluir[0].nunca, true);
  assert.equal(segs.incluir[1].reanalise, true);
  assert.equal(segs.incluir[1].inducao, true);
  assert.equal(segs.incluir[1].nunca, false);
  assert.equal(segs.inaptas[0].motivo, "DEL 36 < 60 dias");
  assert.equal(segs.inaptas[1].lote, "Sem lote");
  assert.equal(segs.inaptas[1].delAtual, null);
  assert.deepEqual(segmentosDaAgenda(null), { aptas: [], incluir: [], inaptas: [] });
});

test("ordenação numérica por coluna, sem DEL sempre no fim; filtro por lote e busca", () => {
  const todos = [...segs.aptas, ...segs.incluir, ...segs.inaptas];
  assert.deepEqual(ordenarAnimais(todos, { col: "n", dir: 1 }).map((a) => a.numero), ["075", "1274", "1296", "2507", "2574", "3335", "9999"]);
  assert.deepEqual(ordenarAnimais(todos, { col: "dp", dir: 1 }).map((a) => a.numero).slice(-1), ["9999"]);
  assert.deepEqual(ordenarAnimais(todos, { col: "dp", dir: -1 }).map((a) => a.numero).slice(-1), ["9999"]);
  assert.equal(ordenarAnimais(todos, { col: "dp", dir: -1 })[0].numero, "075");
  assert.deepEqual(filtrarAnimais(todos, ["01 - Novilhas Alta"], "").map((a) => a.numero), ["2507", "3335"]);
  assert.deepEqual(filtrarAnimais(todos, [], "12").map((a) => a.numero), ["1274", "1296"]);
  assert.equal(filtrarAnimais(todos, [], "").length, 7);
});

test("alvo da ação: aptas + incluir juntas; inaptas nunca se misturam", () => {
  const m: Marcadas = { aptas: new Set(["1274"]), incluir: new Set(["075", "1296"]), inaptas: new Set(["2574"]) };
  assert.deepEqual(alvoDaAcao("aptas", m, segs).map((a) => a.numero), ["1274", "1296", "075"]);
  assert.deepEqual(alvoDaAcao("incluir", m, segs).map((a) => a.numero), ["1274", "1296", "075"]);
  assert.deepEqual(alvoDaAcao("inaptas", m, segs).map((a) => a.numero), ["2574"]);
  assert.deepEqual(reanalisadasMarcadas(m, segs).map((a) => a.numero), ["075"]);
});

test("dose total: por animal × n; total do lote não multiplica; vazio/inválido = null", () => {
  assert.equal(doseTotal({ dose: "2", porAnimal: true }, 3), 6);
  assert.equal(doseTotal({ dose: "2,5", porAnimal: true }, 4), 10);
  assert.equal(doseTotal({ dose: "40", porAnimal: false }, 20), 40);
  assert.equal(doseTotal({ dose: "", porAnimal: true }, 3), null);
  assert.equal(doseTotal({ dose: "0", porAnimal: true }, 3), null);
  assert.equal(doseTotal({ dose: "abc", porAnimal: true }, 3), null);
});

test("previsão do estoque: data futura agenda; sem dose/unidade registra; com dose baixa e mostra o que resta", () => {
  assert.equal(preverEstoque(params({ data: "2026-10-20", dose: "1" }), 5, HOJE, estoque).tipo, "agendar");
  assert.deepEqual(preverEstoque(params(), 5, HOJE, estoque), { tipo: "registrar", n: 5, data: HOJE, motivo: "sem_dose" });
  assert.deepEqual(preverEstoque(params({ dose: "1", unidade: " " }), 5, HOJE, estoque), { tipo: "registrar", n: 5, data: HOJE, motivo: "sem_unidade" });
  const b = preverEstoque(params({ dose: "1" }), 5, HOJE, estoque);
  assert.deepEqual(b, { tipo: "baixar", n: 5, data: HOJE, total: 5, unidade: "unidade", produto: "Lactotropin", restam: 45, saldo: 50 });
  const falta = preverEstoque(params({ dose: "20" }), 5, HOJE, estoque);
  assert.ok(falta.tipo === "baixar" && falta.restam === -50);
  assert.match(textoPrevisao(falta), /o estoque tem só 50/);
  // unidade diferente da do estoque: o servidor converte; a tela não afirma o saldo
  const outra = preverEstoque(params({ dose: "2", unidade: "ml" }), 5, HOJE, estoque);
  assert.ok(outra.tipo === "baixar" && outra.restam === null);
  assert.equal(textoPrevisao(outra), "Vai baixar 10 ml de Lactotropin do estoque.");
  assert.equal(textoPrevisao(b), "Vai baixar 5 unidade de Lactotropin do estoque (restam 45).");
  assert.match(textoPrevisao(preverEstoque(params({ data: "2026-10-20" }), 1, HOJE, estoque)), /^Vai agendar 1 aplicação para 20\/10\/2026/);
});

test("payload de aplicar: o mesmo corpo que o painel antigo mandava", () => {
  const r = montarPayloadAplicar(params({ dose: "1,5", resp: " Marcelo ", porAnimal: false }), ["1274", "2507"]);
  assert.deepEqual(r, { dados: { numeros_matriz: ["1274", "2507"], data_aplicacao: HOJE, aplicado: true, produto: "Lactotropin", dose: 1.5, unidade: "unidade", responsavel: "Marcelo", dose_por_animal: false } });
  const semDose = montarPayloadAplicar(params({ unidade: "", produto: "  " }), ["1"]);
  assert.ok("dados" in semDose && semDose.dados.dose === null && semDose.dados.unidade === null && semDose.dados.produto === "Lactotropin" && semDose.dados.responsavel === undefined);
  assert.deepEqual(montarPayloadAplicar(params(), []), { erro: "Marque ao menos um animal." });
  assert.deepEqual(montarPayloadAplicar(params({ data: "" }), ["1"]), { erro: "Informe a data da aplicação." });
  assert.ok("erro" in montarPayloadAplicar(params({ dose: "x" }), ["1"]));
  assert.ok("erro" in montarPayloadAplicar(params({ dose: "0" }), ["1"]));
});

test("retorno de aplicar: online hoje, online agendado, offline e fila do app", () => {
  const hoje = interpretarRetornoAplicar(
    { aplicados: 2, agendados: 0, programado: false, proxima_aplicacao_calculada: "2026-10-29", avisos: ["Saldo de Lactotropin ficou negativo"] },
    2, params({ dose: "1" }), HOJE, estoque);
  assert.equal(hoje.tipo, "ok");
  assert.match(hoje.texto, /^2 aplicadas em 17\/10\/2026\. Estoque baixou 2 unidade de Lactotropin \(restam 48\)\. Próxima aplicação calculada: 29\/10\/2026\.$/);
  assert.deepEqual(hoje.avisos, ["Saldo de Lactotropin ficou negativo"]);

  // Produto fora do estoque da fazenda: o servidor avisa uma vez por animal e a tela não pode afirmar que baixou.
  const aviso = "\"Lactotropin\" não está no estoque desta fazenda — lançamento registrado sem baixa.";
  const semEstoque = interpretarRetornoAplicar({ aplicados: 2, agendados: 0, avisos: [aviso, aviso] }, 2, params({ dose: "1" }), HOJE, estoque);
  assert.deepEqual(semEstoque.avisos, [aviso]);
  assert.doesNotMatch(semEstoque.texto, /Estoque baixou/);
  assert.match(semEstoque.texto, /O estoque não baixou/);

  const semDose = interpretarRetornoAplicar({ aplicados: 1, agendados: 0 }, 1, params(), HOJE, estoque);
  assert.match(semDose.texto, /^1 aplicada em 17\/10\/2026\. Sem dose e unidade informadas: o estoque não baixou\.$/);

  const ag = interpretarRetornoAplicar({ aplicados: 0, agendados: 3, programado: true }, 3, params({ data: "2026-10-20", dose: "1" }), HOJE, estoque);
  assert.equal(ag.agendou, true);
  assert.match(ag.texto, /^3 agendadas para 20\/10\/2026 — ficam pendentes na Agenda/);

  assert.equal(interpretarRetornoAplicar({ enviado: false }, 2, params(), HOJE, estoque).tipo, "offline");
  const fila = interpretarRetornoAplicar({ enviado: true }, 2, params({ dose: "1" }), HOJE, estoque);
  assert.match(fila.texto, /^2 aplicadas em 17\/10\/2026\./);
  const filaFutura = interpretarRetornoAplicar({ enviado: true }, 2, params({ data: "2026-10-20" }), HOJE, estoque);
  assert.match(filaFutura.texto, /^2 agendadas/);
});

test("retorno de marcar inapta / apta usa a contagem do servidor", () => {
  assert.match(textoRetornoMarcar({ atualizados: 2, inapta: true }, 3, true).texto, /^2 marcadas como inaptas\. Agora estão em “Incluir no próximo BST” com o selo Reanalisar/);
  assert.match(textoRetornoMarcar({ atualizados: 1, inapta: false }, 1, false).texto, /^1 marcada como apta\. Ficou em/);
  assert.match(textoRetornoMarcar({ enviado: true }, 4, true).texto, /^4 marcadas como inaptas/);
  assert.equal(textoRetornoMarcar({ enviado: false }, 4, true).tipo, "offline");
});
