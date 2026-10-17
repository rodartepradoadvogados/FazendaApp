import { test } from "node:test";
import assert from "node:assert/strict";
import {
  agruparCandidatasPorLote, agruparSugestoesPorDestino, alternarItem, codigoDoGrupo, contagemDepois, contagemPorLote, contagensPorSituacao,
  contarForaDoFiltro, corpoServico, dataBr, dataCurta, dataPorExtenso, definirVarios, destinoSugeridoPara, dosesQueFaltam, dosesQueSobram,
  etapasComData, existeEmOutraSituacao, interpretarRespostaMover, lerRecusaAptidao, lotesComCandidatas, marcaveisEmBloco, montarCandidatas,
  origemDoEnvio, passaFiltro, podarSelecao, projetarMovimentacao, recortarPorOrigem, somarDiasIso, soAnimais, statusServico,
  todosMarcados, usoPorTouro, adultosParaLoteDeBezerras, selecaoEfetiva, proximaConfirmacaoPendente, protocoloDaVaca, frasePertenceOutraSituacao,
  type AnimalMovivel, type EstadoReproBase, type LoteBasico,
} from "./lancamentoLote.ts";

// ── seleção ──
test("a seleção persiste: quem fica fora do que se vê continua marcado e é contado", () => {
  let sel = new Set<string>();
  sel = alternarItem(sel, "1045");
  sel = definirVarios(sel, ["1450", "1502"], true);
  assert.equal(sel.size, 3);
  assert.equal(contarForaDoFiltro(sel, ["1045", "9999"]), 2);
  assert.equal(contarForaDoFiltro(sel, []), 3);
});

test("alternar não muda o conjunto original; marcar todos desmarca quando já estão todos", () => {
  const a = new Set(["1"]);
  const b = alternarItem(a, "2");
  assert.equal(a.size, 1);
  assert.deepEqual([...b].sort(), ["1", "2"]);
  assert.equal(todosMarcados(b, ["1", "2"]), true);
  assert.equal(todosMarcados(b, []), false);
  assert.equal(definirVarios(b, ["1", "2"], false).size, 0);
});

test("podarSelecao tira o que não existe mais (rascunho antigo)", () => {
  assert.deepEqual([...podarSelecao(new Set(["1", "2", "3"]), new Set(["2"]))], ["2"]);
});

// ── datas ──
test("datas sem fuso: soma de dias, formato curto e dia por extenso", () => {
  assert.equal(somarDiasIso("2026-10-16", 7), "2026-10-23");
  assert.equal(somarDiasIso("2026-12-30", 3), "2027-01-02");
  assert.equal(dataCurta("2026-10-23"), "23/10");
  assert.equal(dataBr("2026-10-16"), "16/10/2026");
  assert.equal(dataPorExtenso("2026-10-16"), "sexta-feira, 16/10/2026");
});

// ── Movimentar ──
const LOTES: LoteBasico[] = [
  { codigo: "01", nome: "Alta", rotulo: "01 - Alta" }, { codigo: "02", nome: "Média", rotulo: "02 - Média" },
  { codigo: "05", nome: "Pré-parto", rotulo: "05 - Pré-parto" }, { codigo: "07", nome: "Bezerras", rotulo: "07 - Bezerras" },
];
const an = (numero: string, grupo: string | null, extra: Partial<AnimalMovivel> = {}): AnimalMovivel => ({ numero, nome: `V${numero}`, grupo_primario: grupo, ...extra });

test("o lote do animal casa pelo rótulo e, se o nome do lote mudou, pelo número do começo", () => {
  assert.equal(codigoDoGrupo("01 - Alta", LOTES), "01");
  assert.equal(codigoDoGrupo("1 - Nome antigo", LOTES), "01");
  assert.equal(codigoDoGrupo("Sem relação", LOTES), null);
  assert.equal(codigoDoGrupo("", LOTES), null);
});

test("palito de sêmen não entra na lista de movimentação", () => {
  assert.deepEqual(soAnimais([an("1", "01 - Alta"), an("S1", null, { eh_semen: true })]).map((a) => a.numero), ["1"]);
});

test("projeção: quem já está no destino não conta; contagens saem de cada lote de origem", () => {
  const animais = [
    an("1", "01 - Alta"), an("2", "01 - Alta"), an("3", "02 - Média"), an("4", "02 - Média"), an("5", "02 - Média"), an("6", "01 - Alta"),
  ];
  const contagem = contagemPorLote(animais, LOTES);
  assert.equal(contagem.get("01"), 3);
  const marcados = [animais[0], animais[1], animais[2], animais[3]];
  const p = projetarMovimentacao(marcados, LOTES[0], LOTES, contagem);
  assert.deepEqual(p.movem.map((a) => a.numero), ["3", "4"]);
  assert.deepEqual(p.jaAqui.map((a) => a.numero), ["1", "2"]);
  assert.equal(p.destinoAntes, 3);
  assert.equal(p.destinoDepois, 5);
  assert.deepEqual(p.porOrigem.map((o) => [o.codigo, o.antes, o.depois]), [["02", 3, 1]]);
});

test("tudo já no destino = nada a movimentar", () => {
  const animais = [an("1", "01 - Alta")];
  const p = projetarMovimentacao(animais, LOTES[0], LOTES, contagemPorLote(animais, LOTES));
  assert.equal(p.movem.length, 0);
  assert.equal(p.jaAqui.length, 1);
});

test("contagem depois de mover leva só os que o servidor moveu", () => {
  const animais = [an("1", "01 - Alta"), an("2", "01 - Alta"), an("3", "02 - Média")];
  const depois = contagemDepois(animais, LOTES, new Set(["1", "3"]), LOTES[2]);
  assert.equal(depois.get("01"), 1);
  assert.equal(depois.get("02"), undefined);
  assert.equal(depois.get("05"), 2);
});

test("aviso ao mandar adulto para o lote de bezerras", () => {
  const bezerra = an("10", "07 - Bezerras", { categoria_completa: "Bezerra 0-3 meses" });
  const vaca = an("11", "01 - Alta", { categoria_completa: "Vaca em lactação" });
  assert.deepEqual(adultosParaLoteDeBezerras([bezerra, vaca], LOTES[3]).map((a) => a.numero), ["11"]);
  assert.equal(adultosParaLoteDeBezerras([bezerra, vaca], LOTES[0]).length, 0);
});

test("resposta do servidor: brinco que não existe volta em nao_encontrados e não conta como movido", () => {
  assert.deepEqual(interpretarRespostaMover(["1", "2", "3"], { movidos: 2, nao_encontrados: ["2"] }), { movidos: ["1", "3"], naoEncontrados: ["2"] });
  assert.deepEqual(interpretarRespostaMover(["1"], { movidos: 1, nao_encontrados: [] }), { movidos: ["1"], naoEncontrados: [] });
  assert.deepEqual(interpretarRespostaMover(["1"], { movidos: 0, nao_encontrados: [] }), { movidos: [], naoEncontrados: ["1"] });
});

test("sugestões: agrupa pelo primeiro destino indicado, e só vira 'sugestao_passiva' se todos foram para o sugerido", () => {
  const sug = [
    { numero_matriz: "1", lotes_sugeridos: [{ codigo: "01", rotulo: "01 - Alta" }] },
    { numero_matriz: "2", lotes_sugeridos: [{ codigo: "01", rotulo: "01 - Alta" }, { codigo: "02", rotulo: "02 - Média" }] },
    { numero_matriz: "3", lotes_sugeridos: [{ codigo: "05", rotulo: "05 - Pré-parto" }] },
  ];
  assert.deepEqual(agruparSugestoesPorDestino(sug).map((g) => [g.codigo, g.itens.length]), [["01", 2], ["05", 1]]);
  assert.equal(destinoSugeridoPara([an("1", null), an("2", null)], sug), "01");
  assert.equal(destinoSugeridoPara([an("1", null), an("3", null)], sug), null);
  assert.equal(destinoSugeridoPara([an("9", null)], sug), null);
  assert.equal(origemDoEnvio([an("1", null), an("2", null)], "01", sug), "sugestao_passiva");
  assert.equal(origemDoEnvio([an("1", null), an("2", null)], "02", sug), "manual");
  assert.equal(origemDoEnvio([an("1", null), an("9", null)], "01", sug), "manual");
});

// ── Inseminação e Protocolo IATF: quem pode entrar ──
const est = (numero: string, estado: string, extra: Partial<EstadoReproBase> = {}): EstadoReproBase => ({ numero, estado, ...extra });

test("situação de cada vaca diante do serviço", () => {
  assert.equal(statusServico(est("1", "apta"), "ia").pronta, true);
  assert.equal(statusServico(est("1", "atrasada"), "iatf").chip?.rotulo, "Atrasada");
  assert.equal(statusServico(est("1", "pev"), "ia").info, true);
  assert.equal(statusServico(est("1", "nao_apta"), "ia").duro, true);
  assert.equal(statusServico(est("1", "vazia"), "ia").duro, true);
  assert.equal(statusServico(est("1", "gestante", { dias_gestacao: 90 }), "ia").confirmar, true);
  assert.match(statusServico(est("1", "gestante", { dias_gestacao: 90 }), "ia").texto ?? "", /perda da prenhez/);
  assert.doesNotMatch(statusServico(est("1", "gestante"), "iatf").texto ?? "", /perda da prenhez/);
});

test("inseminada recente (< 18 dias) exige confirmação; mais antiga se marca direto", () => {
  assert.equal(statusServico(est("1", "inseminada", { dias_desde_servico: 10 }), "ia").confirmar, true);
  assert.equal(statusServico(est("1", "inseminada", { dias_desde_servico: 17 }), "ia").confirmar, true);
  const velha = statusServico(est("1", "inseminada", { dias_desde_servico: 18 }), "ia");
  assert.equal(velha.confirmar, false);
  assert.equal(velha.info, true);
});

test("vaca em protocolo: travada antes do D11; no D11 a Inseminação libera e o IATF continua travando", () => {
  const d7 = est("1", "em_protocolo", { protocolo_dia_atual: 7 });
  const d11 = est("2", "em_protocolo", { protocolo_dia_atual: 11 });
  assert.equal(statusServico(d7, "ia").travada, true);
  assert.equal(statusServico(d7, "ia").chip?.rotulo, "Em protocolo · D7");
  assert.equal(statusServico(d11, "ia").travada, false);
  assert.equal(statusServico(d11, "ia").d11, true);
  assert.equal(statusServico(d11, "iatf").travada, true);
});

const lista = [
  { numero: "1", nome: "Mimosa", grupo_primario: "01 - Alta" }, { numero: "2", nome: "Estrela", grupo_primario: "01 - Alta" },
  { numero: "3", nome: "Pintada", grupo_primario: "02 - Média" }, { numero: "4", nome: "Bela", grupo_primario: "02 - Média" },
  { numero: "5", nome: "Branca", grupo_primario: "02 - Média" }, { numero: "6", nome: "Nova", grupo_primario: "07 - Bezerras" },
  { numero: "7", nome: "Dona", grupo_primario: "01 - Alta" },
];
const estados = new Map<string, EstadoReproBase>([
  ["1", est("1", "apta", { del_dias: 80 })], ["2", est("2", "atrasada", { del_dias: 130 })], ["3", est("3", "gestante", { dias_gestacao: 100 })],
  ["4", est("4", "em_protocolo", { protocolo_dia_atual: 11 })], ["5", est("5", "pev", { del_dias: 30 })], ["6", est("6", "nao_apta")],
  ["7", est("7", "inseminada", { dias_desde_servico: 5 })],
]);

test("só candidatas entram na lista; bezerra e novilha não apta ficam de fora", () => {
  const cs = montarCandidatas(lista, estados, "ia");
  assert.deepEqual(cs.map((c) => c.numero), ["1", "2", "3", "4", "5", "7"]);
  assert.equal(cs[0].lote, "01 - Alta");
});

test("contagens por situação são escopadas pela origem escolhida", () => {
  const cs = montarCandidatas(lista, estados, "ia");
  const todas = contagensPorSituacao(recortarPorOrigem(cs, { origem: "animais", lotes: new Set(), numerosAgenda: new Set() }));
  assert.deepEqual(todas, { aptas: 1, atrasadas: 1, pev: 1, d11: 1, todas: 6 });
  const lote02 = contagensPorSituacao(recortarPorOrigem(cs, { origem: "lotes", lotes: new Set(["02 - Média"]), numerosAgenda: new Set() }));
  assert.deepEqual(lote02, { aptas: 0, atrasadas: 0, pev: 1, d11: 1, todas: 3 });
  const agenda = recortarPorOrigem(cs, { origem: "agenda", lotes: new Set(), numerosAgenda: new Set(["1", "2"]) });
  assert.deepEqual(agenda.map((c) => c.numero), ["1", "2"]);
});

test("'Selecionar todas' só pega quem se marca sem ler aviso; em Todas, só as prontas", () => {
  const cs = montarCandidatas(lista, estados, "ia");
  assert.deepEqual(marcaveisEmBloco(cs, "todas").map((c) => c.numero), ["1", "2", "4"]);
  assert.deepEqual(marcaveisEmBloco(cs.filter((c) => passaFiltro(c, "aptas")), "aptas").map((c) => c.numero), ["1"]);
  // PEV: no filtro próprio entra em bloco; gestante e inseminada recente nunca
  assert.deepEqual(marcaveisEmBloco(cs.filter((c) => passaFiltro(c, "pev")), "pev").map((c) => c.numero), ["5"]);
});

test("na lista do lote, quem está pronta vem primeiro, atrasadas antes das aptas", () => {
  const cs = montarCandidatas(lista, estados, "ia");
  const g = agruparCandidatasPorLote(cs);
  assert.deepEqual(g.map((x) => x.lote), ["01 - Alta", "02 - Média"]);
  assert.deepEqual(g[0].itens.map((c) => c.numero), ["2", "1", "7"]);
});

test("lotes com candidatas contam só vacas que podem receber serviço", () => {
  const cs = montarCandidatas(lista, estados, "ia");
  assert.deepEqual(lotesComCandidatas(cs), [["01 - Alta", 2], ["02 - Média", 2]]);
});

test("busca por brinco fora do filtro mostra 'existe, mas está gestante'", () => {
  const cs = montarCandidatas(lista, estados, "ia");
  const aptas = cs.filter((c) => passaFiltro(c, "aptas"));
  const outros = existeEmOutraSituacao(cs, aptas, "pintada");
  assert.deepEqual(outros.map((c) => c.numero), ["3"]);
  assert.equal(existeEmOutraSituacao(cs, aptas, "").length, 0);
});

// ── touro e doses ──
test("doses: uso por touro considera a troca vaca a vaca; sobra e falta nunca ficam negativas", () => {
  const troca: Record<string, string> = { "2": "Raro" };
  const uso = usoPorTouro(["1", "2", "3"], (n) => troca[n] ?? "Padrão");
  assert.deepEqual(uso, { Padrão: 2, Raro: 1 });
  assert.equal(dosesQueSobram(14, 8), 6);
  assert.equal(dosesQueSobram(3, 8), 0);
  assert.equal(dosesQueFaltam(3, 8), 5);
  assert.equal(dosesQueFaltam(14, 8), 0);
});

test("corpo do serviço: monta natural não leva tipo_semen; forcar e protocolo só quando existem", () => {
  const ia = corpoServico({ numero: "1", data: "2026-10-16", categoria: "sexado", touro: "Raro", protocolo: "PROTOCOLO IATF - X", confirmada: true });
  assert.deepEqual(ia, {
    numero_matriz: "1", data_servico: "2026-10-16", tipo_servico: "IA", reprodutor: "Raro", tipo_semen: "sexado",
    protocolo: "PROTOCOLO IATF - X", forcar: true,
  });
  const monta = corpoServico({ numero: "2", data: "2026-10-16", categoria: "fazenda", touro: "", confirmada: false });
  assert.equal(monta.tipo_servico, "Monta natural");
  assert.equal(monta.tipo_semen, undefined);
  assert.equal(monta.reprodutor, undefined);
  assert.equal(monta.forcar, undefined);
  assert.equal(monta.protocolo, undefined);
});

// ── IATF ──
test("linha do tempo do IATF: D0, D7, D9 e D11 com as datas calculadas", () => {
  const e = etapasComData("2026-10-16");
  assert.deepEqual(e.map((x) => [x.dia, x.dataCurta]), [[0, "16/10"], [7, "23/10"], [9, "25/10"], [11, "27/10"]]);
  assert.equal(etapasComData("")[1].dataCurta, "");
});

test("recusa de aptidão (409) é lida do corpo; outro erro não vira recusa", () => {
  const r = lerRecusaAptidao(409, { erro: "aptidao", msg: "2 animal(is) do lote não estão aptos", motivo: "gestante", confirmavel: true, animais: ["1029", "1450"] }, "padrão");
  assert.deepEqual(r, { mensagem: "2 animal(is) do lote não estão aptos", motivo: "gestante", confirmavel: true, animais: ["1029", "1450"] });
  assert.equal(lerRecusaAptidao(409, { erro: "aptidao", confirmavel: false }, "padrão")?.mensagem, "padrão");
  assert.equal(lerRecusaAptidao(409, { erro: "outra" }, "x"), null);
  assert.equal(lerRecusaAptidao(400, { erro: "aptidao" }, "x"), null);
  assert.equal(lerRecusaAptidao(409, "texto", "x"), null);
});

test("sugestões sem lote indicado ficam de fora do agrupamento", () => {
  assert.equal(agruparSugestoesPorDestino([{ numero_matriz: "1", lotes_sugeridos: [] }]).length, 0);
});

// ── seleção efetiva (B1) ──
test("marca antiga não fura a regra: travada sai, 'confirmar' sem confirmação sai, confirmada fica", () => {
  const e2 = new Map<string, EstadoReproBase>([
    ["1", est("1", "apta")], ["2", est("2", "inseminada", { dias_desde_servico: 5 })], ["3", est("3", "em_protocolo", { protocolo_dia_atual: 4 })],
    ["4", est("4", "gestante")], ["5", est("5", "pev")],
  ]);
  const cs = montarCandidatas(["1", "2", "3", "4", "5", "9"].map((n) => ({ numero: n })), e2, "ia");
  const r = selecaoEfetiva(new Set(["1", "2", "3", "4", "5", "9"]), new Set(["4"]), cs);
  assert.deepEqual([...r.sel].sort(), ["1", "4", "5"]);
  assert.deepEqual([...r.confirmadas], ["4"]);
  // confirmação de quem nem está marcado não vale
  assert.equal(selecaoEfetiva(new Set(["1"]), new Set(["4"]), cs).confirmadas.size, 0);
});

test("vaca trazida da ficha que exige confirmação abre o sheet; some depois de aceita ou dispensada", () => {
  const e2 = new Map<string, EstadoReproBase>([["2", est("2", "inseminada", { dias_desde_servico: 5 })], ["1", est("1", "apta")]]);
  const cs = montarCandidatas([{ numero: "1" }, { numero: "2" }], e2, "ia");
  assert.equal(proximaConfirmacaoPendente(["2"], new Set(), new Set(), cs)?.numero, "2");
  assert.equal(proximaConfirmacaoPendente(["2"], new Set(["2"]), new Set(), cs), null);
  assert.equal(proximaConfirmacaoPendente(["2"], new Set(), new Set(["2"]), cs), null);
  assert.equal(proximaConfirmacaoPendente(["1"], new Set(), new Set(), cs), null);
});

test("vínculo D11: casa pelo D0 do estado da vaca, nunca pelo protocolo mais antigo", () => {
  const ativos = [
    { nome_protocolo: "NOVO", data_d0: "2026-10-06", animais: [{ numero_matriz: "1", pronta_para_inseminar: true }] },
    { nome_protocolo: "VELHO", data_d0: "2026-09-01", animais: [{ numero_matriz: "1", pronta_para_inseminar: true }] },
  ];
  assert.equal(protocoloDaVaca(ativos, "1", "2026-10-06"), "NOVO");
  assert.equal(protocoloDaVaca(ativos, "1", "2026-09-01"), "VELHO");
  assert.equal(protocoloDaVaca(ativos, "1", "2026-08-01"), null);
  assert.equal(protocoloDaVaca(ativos, "1", null), null);
  assert.equal(protocoloDaVaca(ativos, "2", "2026-10-06"), null);
});

test("frase de outra situação mantém a caixa do rótulo", () => {
  const c = montarCandidatas([{ numero: "1", nome: "Mimosa" }], new Map([["1", est("1", "em_protocolo", { protocolo_dia_atual: 7 })]]), "ia")[0];
  assert.equal(frasePertenceOutraSituacao(c), "1 Mimosa existe, mas está em protocolo · D7.");
});
