import { test } from "node:test";
import assert from "node:assert/strict";
import {
  alternaAptas, agrupaPorLote, aptidaoDe, contagemFaixa, filtraLinhas, motivoCurto, montarLinhas, resumoSelecao, semBloqueadas,
  type LinhaFemea,
} from "./aptidaoServico.ts";
import type { AptidaoServicoApi } from "./api.ts";

const API: AptidaoServicoApi = {
  data: "2026-10-17", idade_min_meses: 15, peso_min_kg: 300,
  animais: {
    "13204": { motivo: "idade", mensagem: "13204 tem 11.0 meses — abaixo da idade mínima de aptidão (15 meses, em Configurações > Parâmetros).", confirmavel: false },
    "1110": { motivo: "peso", mensagem: "1110 pesou 240 kg na última pesagem — abaixo do peso mínimo de aptidão (300 kg, em Configurações > Parâmetros).", confirmavel: true },
    "8012": { motivo: "gestante", mensagem: "8012 consta como GESTANTE (serviço de 10/05/2026). Lançar um serviço novo registra a perda da prenhez atual.", confirmavel: true },
  },
  em_protocolo: { "7120": { lancamento_id: 1, nome_protocolo: "PROTOCOLO IATF - 06/10/26 A 17/10/26 (D0 A D11 - 12 DIAS)", data_d0: "2026-10-06" } },
};

test("motivo curto: sem o número, sem parêntese de configuração, só a primeira frase", () => {
  assert.equal(motivoCurto(API.animais["13204"].mensagem, "13204"), "Tem 11,0 meses — abaixo da idade mínima de aptidão");
  assert.equal(motivoCurto(API.animais["8012"].mensagem, "8012"), "Consta como GESTANTE (serviço de 10/05/2026)");
  assert.equal(motivoCurto(null), "");
});

test("o servidor manda: confirmável vira 'confirmar'; duro vira 'bloqueada'; ausente é apta", () => {
  assert.equal(aptidaoDe({ numero: "1110", api: API }).nivel, "confirmar");
  assert.equal(aptidaoDe({ numero: "8012", api: API }).nivel, "confirmar");
  const dura = aptidaoDe({ numero: "13204", api: API });
  assert.equal(dura.nivel, "bloqueada");
  assert.equal(dura.codigo, "idade");
  assert.equal(aptidaoDe({ numero: "11153", api: API }).nivel, "apta");
});

test("já em protocolo IATF vigente: bloqueada com o motivo em texto, só quando a trava está ligada", () => {
  const ligada = aptidaoDe({ numero: "7120", api: API, bloquearEmProtocolo: true });
  assert.equal(ligada.nivel, "bloqueada");
  assert.equal(ligada.codigo, "em_protocolo");
  assert.match(ligada.motivo ?? "", /Já em protocolo IATF vigente/);
  assert.match(ligada.detalhe ?? "", /06\/10\/2026/);
  assert.equal(aptidaoDe({ numero: "7120", api: API, bloquearEmProtocolo: false }).nivel, "apta");
});

test("modo 'adicionar a um em andamento': quem já está no protocolo escolhido é 'já está neste protocolo'", () => {
  const a = aptidaoDe({ numero: "7120", api: API, bloquearEmProtocolo: true, protocoloDestinoId: 1 });
  assert.equal(a.codigo, "neste_protocolo");
  assert.equal(aptidaoDe({ numero: "7120", api: API, bloquearEmProtocolo: true, protocoloDestinoId: 2 }).codigo, "em_protocolo");
});

test("sem a resposta do servidor: vale o que a página antecipa (duro) e o estado 'gestante' (confirmável)", () => {
  const locais = new Map([["13204", "11,0 meses — mínimo 15"]]);
  assert.equal(aptidaoDe({ numero: "13204", api: null, motivosLocais: locais }).nivel, "bloqueada");
  assert.equal(aptidaoDe({ numero: "8012", api: null, gestanteLocal: true }).nivel, "confirmar");
  assert.equal(aptidaoDe({ numero: "11153", api: null }).nivel, "apta");
});

const animais = [
  { numero: "11153", grupo_primario: "02 - Vacas Alta", categoria_abrev: "Vaca", del_dias: 96, em_lactacao: true },
  { numero: "8012", grupo_primario: "02 - Vacas Alta", categoria_abrev: "Vaca", del_dias: 187, em_lactacao: true },
  { numero: "7120", grupo_primario: "02 - Vacas Alta", categoria_abrev: "Vaca", del_dias: 74, em_lactacao: true },
  { numero: "13204", grupo_primario: "13 - Novilhas Novas", categoria_abrev: "Novilha", idade_meses: 11.4 },
  { numero: "1110", grupo_primario: "01 - Novilhas Alta", categoria_abrev: "Novilha", idade_meses: 16.2 },
  { numero: "999", grupo_primario: null, categoria_abrev: null },
];
const estados = new Map([
  ["11153", { estado: "vazia", del_dias: 96, data_servico: "2026-08-05", tipo_servico: "IA" }],
  ["8012", { estado: "gestante", del_dias: 187, data_servico: "2026-05-10", tipo_servico: "Monta natural" }],
]);
const linhas = (extra = {}) => montarLinhas({ animais, estados, rotuloEstado: (n) => (n === "8012" ? "Gestante" : "Vazia"), api: API, bloquearEmProtocolo: true, ...extra });

test("linhas: marco (DEL ou meses), última IA/monta, selo do protocolo e lote 'Sem lote'", () => {
  const l = Object.fromEntries(linhas().map((x) => [x.numero, x]));
  assert.equal(l["11153"].marco, "DEL 96");
  assert.equal(l["11153"].ultima, "IA 05/08/2026");
  assert.equal(l["8012"].ultima, "Monta 10/05/2026");
  assert.equal(l["13204"].marco, "11 meses");
  assert.equal(l["7120"].protocolo, "IATF 06/10");
  assert.equal(l["999"].lote, "Sem lote");
  assert.equal(l["999"].marco, "—");
  assert.equal(l["11153"].ultima === "—", false);
  assert.equal(l["1110"].ultima, "—");
});

test("indução de cio: a aptidão é só informativa — nunca bloqueia, vira 'confira'", () => {
  const l = Object.fromEntries(linhas({ usarServidor: false, motivosLocais: new Map([["13204", "11,0 meses — mínimo 15"]]) }).map((x) => [x.numero, x]));
  assert.equal(l["13204"].aptidao.nivel, "confirmar");
  assert.equal(l["7120"].aptidao.nivel, "apta");
});

test("'marcar as aptas' nunca entra sozinha com quem pede confirmação ou está bloqueada, e desmarca quando todas já estão", () => {
  const ls = linhas();
  const s1 = alternaAptas(new Set(), ls);
  assert.deepEqual([...s1].sort(), ["11153", "999"]); // 8012 e 1110 pedem confirmação; 13204 e 7120 bloqueadas
  assert.equal(alternaAptas(s1, ls).size, 0);
});

test("agrupa por lote em ordem numérica e filtra por busca sem acento", () => {
  const g = agrupaPorLote(linhas());
  assert.deepEqual(g.map((x) => x.lote), ["01 - Novilhas Alta", "02 - Vacas Alta", "13 - Novilhas Novas", "Sem lote"]);
  assert.deepEqual(filtraLinhas(linhas(), "novilhas").map((x) => x.numero).sort(), ["1110", "13204"]);
  assert.deepEqual(filtraLinhas(linhas(), "  8012 ").map((x) => x.numero), ["8012"]);
});

test("resumo e faixa: contam apta, pede confirmação e bloqueada", () => {
  const ls = linhas();
  const r = resumoSelecao(ls, new Set(["11153", "8012", "1110"]));
  assert.equal(r.total, 3);
  assert.equal(r.pedemConfirmacao, 2);
  assert.deepEqual(contagemFaixa(ls), { total: 6, aptas: 2, confirmar: 2, bloqueadas: 2 });
});

test("o veredito mudou (nova data, protocolo lançado): bloqueada sai da seleção", () => {
  const ls = linhas();
  assert.deepEqual([...semBloqueadas(new Set(["11153", "13204", "7120"]), ls)], ["11153"]);
});

test("pré-marcada vem do conjunto informado", () => {
  const l = linhas({ preMarcadas: new Set(["11153"]) }) as LinhaFemea[];
  assert.equal(l.find((x) => x.numero === "11153")?.preMarcada, true);
  assert.equal(l.find((x) => x.numero === "8012")?.preMarcada, false);
});

test("cio natural / monta natural datados ANTES do D0 do protocolo não conflitam com ele (igual ao servidor)", () => {
  assert.equal(aptidaoDe({ numero: "7120", api: API, bloquearEmProtocolo: true, dataReferencia: "2026-10-05" }).nivel, "apta");
  assert.equal(aptidaoDe({ numero: "7120", api: API, bloquearEmProtocolo: true, dataReferencia: "2026-10-06" }).nivel, "bloqueada");
});
