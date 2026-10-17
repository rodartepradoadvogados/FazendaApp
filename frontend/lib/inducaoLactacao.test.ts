import test from "node:test";
import assert from "node:assert/strict";
import {
  avisosElegibilidade, celulaCronograma, descreverDia, diaDaEtapa, diaInicioOrdenha, eventosNaAgenda, formatarIdade, indexarAtivosPorAnimal,
  linhasDoCronograma, linhasEmAndamento, montarPayloadInducao, nomeCurto, proximaOrdenha, resumoDoProtocolo, rotuloD,
  type InducaoAtiva, type ProtocoloInducao,
} from "./inducaoLactacao.ts";

const protocolo: ProtocoloInducao = {
  id: 7, nome: "Protocolo de Indução de Lactação — 28 dias (Ativos 1)", dia_inicial: 0, duracao_dias: 27, observacao: "Manter a bST",
  etapas: [
    { dia: 0, tipo: "medicamento", produto: "Somatotropina Bovina (bST)", unidade: "dose" },
    { dia: 0, tipo: "dispositivo", produto: "Implante de Progesterona", acao_dispositivo: "colocar" },
    { dia: 0, tipo: "medicamento", produto: "Benzoato de Estradiol", dose: 30, unidade: "ml" },
    { dia: 1, tipo: "medicamento", produto: "Benzoato de Estradiol", dose: 30, unidade: "ml" },
    { dia: 7, tipo: "dispositivo", produto: "Implante de Progesterona", acao_dispositivo: "retirar" },
    { dia: 16, tipo: "manejo", produto: "Adaptação na ordenha" },
    { dia: 21, tipo: "manejo", produto: "COMEÇAR A ORDENHA" },
  ],
};

test("nome curto e rótulo do primeiro dia", () => {
  assert.equal(nomeCurto(protocolo.nome), "Ativos 1");
  assert.equal(nomeCurto("Indução simples"), "Indução simples");
  assert.equal(rotuloD(protocolo), "D0");
  assert.equal(rotuloD({ dia_inicial: 1 }), "D1");
  assert.equal(rotuloD(undefined), "D0");
});

test("eventos na Agenda = dias distintos do cronograma × animais (a mesma conta do servidor)", () => {
  assert.equal(eventosNaAgenda(protocolo, 1), 5); // dias 0, 1, 7, 16, 21
  assert.equal(eventosNaAgenda(protocolo, 3), 15);
  assert.equal(eventosNaAgenda(protocolo, 0), 0);
});

test("dia do início da ordenha ignora a adaptação", () => {
  assert.equal(diaInicioOrdenha(protocolo), 21);
  assert.equal(diaInicioOrdenha({ ...protocolo, etapas: protocolo.etapas.filter((e) => e.dia !== 21) }), null);
  assert.equal(diaInicioOrdenha({ ...protocolo, etapas: [{ dia: 18, tipo: "manejo", produto: "INICIAR A ORDENHA" }] }), 18);
});

test("cronograma: uma linha por produto, implante e remédio antes do manejo", () => {
  const l = linhasDoCronograma(protocolo);
  assert.deepEqual(l.map((x) => x.rotulo), ["Implante de progesterona", "bST (somatotropina)", "Benzoato de Estradiol", "Adaptação na ordenha", "COMEÇAR A ORDENHA"]);
  assert.equal(l[0].tipo, "dispositivo");
  const implante = l.find((x) => x.rotulo === "Implante de progesterona")!;
  assert.deepEqual([...implante.porDia.keys()], [0, 7]);
  assert.equal(l.find((x) => x.rotulo === "Benzoato de Estradiol")!.unidade, "ml");
  assert.equal(l[l.length - 1].tipo, "manejo");
});

test("células e descrição do dia", () => {
  assert.equal(celulaCronograma(protocolo.etapas[1]).texto, "▼");
  assert.equal(celulaCronograma(protocolo.etapas[4]).texto, "▲");
  assert.equal(celulaCronograma(protocolo.etapas[2]).texto, "30");
  assert.equal(celulaCronograma(protocolo.etapas[0]).texto, "●");
  assert.equal(celulaCronograma(protocolo.etapas[6]).texto, "▶");
  assert.equal(celulaCronograma(protocolo.etapas[5]).texto, "●");
  assert.match(descreverDia(protocolo, 0), /Colocar implante de progesterona/);
  assert.match(descreverDia(protocolo, 0), /Benzoato de Estradiol 30 ml/);
  assert.equal(descreverDia(protocolo, 21), "COMEÇAR A ORDENHA");
});

test("resumo do cartão cita os produtos e o dia da ordenha", () => {
  const r = resumoDoProtocolo(protocolo);
  assert.match(r, /a ordenha começa no D21/);
  assert.match(r, /Benzoato de Estradiol/);
});

test("em andamento: casa com o molde (etapa, dia do protocolo, ordenha) e cai no básico sem ele", () => {
  const ativa: InducaoAtiva = {
    lancamento_id: 1, protocolo_id: 7, nome_protocolo: "Ativos 1 — D0 06/10", data_d0: "2026-10-06",
    animais: [{ numero_matriz: "4802", etapa_atual: "D7", data_etapa_atual: "2026-10-13" }],
  };
  const [l] = linhasEmAndamento(ativa, protocolo);
  assert.equal(l.numero, "4802");
  assert.match(l.descricao, /Retirar implante/);
  assert.equal(l.diaProtocolo, "D7 de 27");
  assert.equal(l.ordenha, "2026-10-27");
  const [b] = linhasEmAndamento(ativa, undefined);
  assert.deepEqual([b.descricao, b.diaProtocolo, b.ordenha], ["", "D7", null]);
  assert.equal(diaDaEtapa("D11"), 11);
  assert.equal(diaDaEtapa("Concluído"), null);
});

test("próxima ordenha: só de hoje em diante, a mais cedo", () => {
  assert.equal(proximaOrdenha(["2026-10-01", "2026-10-27", "2026-10-20", null], "2026-10-17"), "2026-10-20");
  assert.equal(proximaOrdenha(["2026-10-01"], "2026-10-17"), null);
  assert.equal(proximaOrdenha([], "2026-10-17"), null);
});

test("avisos de elegibilidade só informam e saem na ordem: indução, prenha, lactação", () => {
  assert.deepEqual(avisosElegibilidade({}, undefined, undefined), []);
  assert.deepEqual(avisosElegibilidade({ em_lactacao: true, del_dias: 118 }, undefined, undefined), ["Em lactação (118 DEL)"]);
  assert.deepEqual(avisosElegibilidade({ em_lactacao: false }, { estado: "gestante", dias_gestacao: 142 }, undefined), ["Prenha há 142 dias"]);
  assert.deepEqual(avisosElegibilidade({ em_lactacao: false }, { estado: "vazia", dias_gestacao: null }, undefined), []);
  assert.deepEqual(
    avisosElegibilidade({ em_lactacao: true }, { estado: "gestante", dias_gestacao: null }, { nome: "Indução (Ativos 1)", etapa: "D11" }),
    ["Já em indução (Ativos 1 · D11)", "Prenha", "Em lactação"],
  );
});

test("indexa as induções ativas por animal; a de D0 mais recente vence", () => {
  const m = indexarAtivosPorAnimal([
    { lancamento_id: 1, nome_protocolo: "Antiga", data_d0: "2026-09-01", animais: [{ numero_matriz: "1", etapa_atual: "D20", data_etapa_atual: null }] },
    { lancamento_id: 2, nome_protocolo: "Nova", data_d0: "2026-10-06", animais: [{ numero_matriz: "1", etapa_atual: "D5", data_etapa_atual: null }, { numero_matriz: "2", etapa_atual: "D5", data_etapa_atual: null }] },
  ]);
  assert.deepEqual(m.get("1"), { nome: "Nova", etapa: "D5" });
  assert.equal(m.size, 2);
});

test("idade: meses até 47, anos depois", () => {
  assert.equal(formatarIdade(1), "1 mês");
  assert.equal(formatarIdade(27), "27 meses");
  assert.equal(formatarIdade(48), "4 anos");
  assert.equal(formatarIdade(null), "—");
});

test("payload: protocolo, animal e data do D0/D1 são obrigatórios; opcionais vazios saem undefined", () => {
  const base = { protocoloId: "7", protocolo, animais: ["4802"], dataD0: "2026-10-19", responsavel: "", observacao: "  " };
  assert.deepEqual(montarPayloadInducao(base), { dados: { protocolo_id: 7, animais: ["4802"], data_d0: "2026-10-19", responsavel: undefined, observacao: undefined } });
  assert.deepEqual(montarPayloadInducao({ ...base, responsavel: "Marcelo", observacao: " pasto " }), { dados: { protocolo_id: 7, animais: ["4802"], data_d0: "2026-10-19", responsavel: "Marcelo", observacao: "pasto" } });
  assert.deepEqual(montarPayloadInducao({ ...base, protocoloId: "" }), { erro: "Selecione o protocolo de indução." });
  assert.deepEqual(montarPayloadInducao({ ...base, animais: [] }), { erro: "Selecione ao menos uma matriz (ou lote)." });
  assert.deepEqual(montarPayloadInducao({ ...base, dataD0: "" }), { erro: "Informe a data do D0." });
  assert.deepEqual(montarPayloadInducao({ ...base, protocolo: { ...protocolo, dia_inicial: 1 }, dataD0: "" }), { erro: "Informe a data do D1." });
});
