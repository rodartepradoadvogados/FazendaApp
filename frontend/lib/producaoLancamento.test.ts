import { test } from "node:test";
import assert from "node:assert/strict";
import {
  aplicadoEfetivo, agruparPorLote, diasEntre, erroDeSecagem, faixaControle, faixaPesagem, hojeLocalIso, jaTemControleNaData, mensagemDoErro,
  montarEntradasControle, montarEntradasPesagem, numOuNull, ordenhasParaEnvio, passaFiltroSecagem, pesoValido, produtosParaEnvio,
  resumoErros, situacaoSecagem, sobreAnterior, somarDiasIso, totalAplicado, totalDaVaca, vacaEmLactacao, vacasDoLoteParaControle,
  variacaoControle,
} from "./producaoLancamento.ts";

// ── datas e números ──
test("hoje é o calendário local, não o UTC", () => {
  assert.equal(hojeLocalIso(new Date(2026, 9, 17, 22, 30)), "2026-10-17");
});
test("dias entre datas e soma de dias, inclusive virada de mês", () => {
  assert.equal(diasEntre("2026-09-28", "2026-10-17"), 19);
  assert.equal(somarDiasIso("2026-10-30", 3), "2026-11-02");
});
test("campo em branco é null, nunca 0; vírgula decimal é aceita", () => {
  assert.equal(numOuNull(""), null);
  assert.equal(numOuNull("  "), null);
  assert.equal(numOuNull(undefined), null);
  assert.equal(numOuNull("11,2"), 11.2);
  assert.equal(numOuNull("0"), 0);
});
test("agrupa por lote em ordem numérica e junta quem não tem lote", () => {
  const g = agruparPorLote([{ l: "10 - A" }, { l: "02 - B" }, { l: null }], (x) => x.l);
  assert.deepEqual(g.map(([k]) => k), ["02 - B", "10 - A", "Sem lote"]);
});

// ── Controle leiteiro ──
test("em lactação: a flag da API manda; sem a flag cai no critério antigo", () => {
  assert.equal(vacaEmLactacao({ numero: "1", em_lactacao: false, del_dias: 200, grupo_primario: "02 - Alta" }, ["02 - Alta"]), false);
  assert.equal(vacaEmLactacao({ numero: "1", em_lactacao: true }, []), true);
  assert.equal(vacaEmLactacao({ numero: "1", grupo_primario: "02 - Alta" }, ["02 - Alta"]), true);
  assert.equal(vacaEmLactacao({ numero: "1", del_dias: 5 }, []), true);
  assert.equal(vacaEmLactacao({ numero: "1", del_dias: 0 }, []), false);
});
test("por lote entram só as vacas com lactação aberta (o servidor recusa o lote inteiro por uma) e conta as que ficaram de fora", () => {
  const animais = [
    { numero: "1", grupo_primario: "02", em_lactacao: true }, { numero: "2", grupo_primario: "02", em_lactacao: false },
    { numero: "3", grupo_primario: "02" }, { numero: "4", grupo_primario: "05", em_lactacao: true },
  ];
  const r = vacasDoLoteParaControle(animais, ["02"]);
  assert.deepEqual(r.vacas.map((v) => v.numero), ["1", "3"]);
  assert.equal(r.foraDaLactacao, 1);
});
test("ordenha em branco vira null e não entra na soma; 2 ou 3 ordenhas", () => {
  assert.deepEqual(ordenhasParaEnvio(["10,5", "", "7"], 2), [10.5, null]);
  assert.deepEqual(ordenhasParaEnvio(["10", "", "7"], 3), [10, null, 7]);
  assert.deepEqual(ordenhasParaEnvio(undefined, 2), [null, null]);
  assert.equal(totalDaVaca(["10", "5"], 2), 15);
  assert.equal(totalDaVaca(["10", "5", "4"], 2), 15);
  assert.equal(totalDaVaca(["", ""], 2), null);
});
test("zero digitado é uma ordenha real (zerou); só vai a vaca com pelo menos uma ordenha", () => {
  const e = montarEntradasControle(["1", "2", "3"], { "1": ["12", ""], "2": ["", ""], "3": ["0", ""] }, 2);
  assert.deepEqual(e, [{ numero_matriz: "1", ordenhas: [12, null] }, { numero_matriz: "3", ordenhas: [0, null] }]);
});
test("variação sobre o último controle: 25% ou mais pede conferência", () => {
  const ult = { producao_kg: 20, producao_data: "2026-10-03", producao_origem: "controle" as const };
  assert.deepEqual(variacaoControle(22, ult, "2026-10-17"), { pct: 10, conferir: false });
  assert.equal(variacaoControle(15, ult, "2026-10-17")?.conferir, true);
  assert.equal(variacaoControle(112, ult, "2026-10-17")?.conferir, true);
  assert.equal(variacaoControle(null, ult, "2026-10-17"), null);
});
test("sem base confiável não há variação: dado congelado do Ideagri, sem último controle, ou último já desta data", () => {
  assert.equal(variacaoControle(30, { producao_kg: 20, producao_data: "2026-01-01", producao_origem: "congelado" }, "2026-10-17"), null);
  assert.equal(variacaoControle(30, { producao_kg: null, producao_data: null, producao_origem: null }, "2026-10-17"), null);
  assert.equal(variacaoControle(30, { producao_kg: 20, producao_data: "2026-10-17", producao_origem: "controle" }, "2026-10-17"), null);
});
test("lançar de novo na mesma data substitui o registro do dia", () => {
  assert.equal(jaTemControleNaData({ producao_data: "2026-10-17", producao_origem: "controle" }, "2026-10-17"), true);
  assert.equal(jaTemControleNaData({ producao_data: "2026-10-03", producao_origem: "controle" }, "2026-10-17"), false);
  assert.equal(jaTemControleNaData({ producao_data: "2026-10-17", producao_origem: "congelado" }, "2026-10-17"), false);
});
test("faixa do controle: último controle, média daquele dia e quem está sem controle há mais de 30 dias", () => {
  const f = faixaControle([
    { numero: "1", producao_kg: 20, producao_data: "2026-10-03", producao_origem: "controle" },
    { numero: "2", producao_kg: 30, producao_data: "2026-10-03", producao_origem: "controle" },
    { numero: "3", producao_kg: 25, producao_data: "2026-08-01", producao_origem: "controle" },   // velho
    { numero: "4", producao_kg: 18, producao_data: null, producao_origem: "congelado" },          // Ideagri
    { numero: "5" },                                                                               // nunca
  ], "2026-10-17");
  assert.deepEqual(f, { vacas: 5, ultimoControle: "2026-10-03", mediaUltimo: 25, semControle: 3 });
  assert.deepEqual(faixaControle([], "2026-10-17"), { vacas: 0, ultimoControle: null, mediaUltimo: null, semControle: 0 });
});
test("erros da planilha: as primeiras mensagens e quantas ficaram de fora", () => {
  assert.deepEqual(resumoErros(["a", "b", "c"], 2), { primeiras: ["a", "b"], resto: 1 });
  assert.deepEqual(resumoErros(["a"], 5), { primeiras: ["a"], resto: 0 });
});

// ── Pesagem corporal ──
test("só vai peso maior que zero", () => {
  assert.equal(pesoValido("350"), 350);
  assert.equal(pesoValido("350,5"), 350.5);
  assert.equal(pesoValido("0"), null);
  assert.equal(pesoValido(""), null);
  assert.equal(pesoValido("-5"), null);
  assert.deepEqual(montarEntradasPesagem(["1", "2", "3"], { "1": "300", "2": "0", "3": "" }), [{ numero_matriz: "1", peso_kg: 300 }]);
});
test("ganho e GMD sobre a pesagem anterior", () => {
  const r = sobreAnterior(330, { ultima_data: "2026-09-27", ultima_peso: 300 }, "2026-10-17");
  assert.equal(r.dias, 20);
  assert.equal(r.ganho, 30);
  assert.equal(r.gmd, 1.5);
  assert.equal(r.jaPesada, false);
});
test("perda de peso aparece como ganho negativo", () => {
  const r = sobreAnterior(294, { ultima_data: "2026-09-27", ultima_peso: 300 }, "2026-10-17");
  assert.equal(r.ganho, -6);
  assert.ok((r.gmd ?? 0) < 0);
});
test("sem pesagem anterior é a 1ª pesagem; com peso em branco não há nada a mostrar", () => {
  assert.equal(sobreAnterior(262, null, "2026-10-17").primeira, true);
  assert.equal(sobreAnterior(null, null, "2026-10-17").primeira, false);
  const r = sobreAnterior(null, { ultima_data: "2026-09-27", ultima_peso: 300 }, "2026-10-17");
  assert.equal(r.ganho, null);
  assert.equal(r.dias, 20);
});
test("último peso da própria data (ou posterior) não gera ganho: lançar de novo substitui o do dia", () => {
  const r = sobreAnterior(310, { ultima_data: "2026-10-17", ultima_peso: 300 }, "2026-10-17");
  assert.equal(r.jaPesada, true);
  assert.equal(r.ganho, null);
  assert.equal(r.gmd, null);
  assert.equal(sobreAnterior(310, { ultima_data: "2026-10-20", ultima_peso: 300 }, "2026-10-17").jaPesada, true);
});
test("faixa da pesagem: última pesagem, GMD médio e quem já foi pesado mas está há mais de 60 dias sem pesar", () => {
  const f = faixaPesagem(85, [
    { numero_matriz: "1", ultima_data: "2026-09-28", gmd_kg_dia: 0.8 },
    { numero_matriz: "2", ultima_data: "2026-06-01", gmd_kg_dia: 0.6 },
    { numero_matriz: "3", ultima_data: "2026-09-28", gmd_kg_dia: null },
  ], "2026-10-17");
  assert.equal(f.animais, 85);
  assert.equal(f.ultimaPesagem, "2026-09-28");
  assert.ok(Math.abs((f.gmdMedio ?? 0) - 0.7) < 1e-9);
  assert.equal(f.semPesar, 1);
  assert.deepEqual(faixaPesagem(0, [], "2026-10-17"), { animais: 0, ultimaPesagem: null, gmdMedio: null, semPesar: 0 });
});

// ── Secagem ──
test("situação da secagem: atrasada, hoje, em breve, longe e sem prenhez", () => {
  assert.equal(situacaoSecagem(-8).texto, "Atrasada 8 d");
  assert.equal(situacaoSecagem(-8).tom, "atencao");
  assert.equal(situacaoSecagem(0).texto, "Hoje");
  assert.deepEqual([situacaoSecagem(5).tom, situacaoSecagem(5).texto], ["ok", "Em 5 d"]);
  assert.deepEqual([situacaoSecagem(40).tom, situacaoSecagem(40).texto], ["neutro", "Em 40 d"]);
  assert.equal(situacaoSecagem(null).texto, "Sem prenhez confirmada");
  assert.equal(situacaoSecagem(10, false).texto, "Não precisa secar");
});
test("filtros: até 30 dias inclui as atrasadas; atrasadas só as negativas; sem prenhez só em 'todas'", () => {
  assert.equal(passaFiltroSecagem("proximas", -3), true);
  assert.equal(passaFiltroSecagem("proximas", 30), true);
  assert.equal(passaFiltroSecagem("proximas", 31), false);
  assert.equal(passaFiltroSecagem("atrasadas", 0), false);
  assert.equal(passaFiltroSecagem("atrasadas", -1), true);
  assert.equal(passaFiltroSecagem("proximas", null), false);
  assert.equal(passaFiltroSecagem("todas", null), true);
});
test("produtos: só os completos; 'total' divide pelo nº de vacas e usa o índice original", () => {
  const itens = [
    { produto: "", via: "", quantidade: "5", unidade: "ml" },                       // sem produto: fora
    { produto: "Cepravin", via: "Intramamária", quantidade: "1", unidade: "unidade" },
    { produto: "Vit E", via: "", quantidade: "40", unidade: "ml" },
    { produto: "Zero", via: "", quantidade: "0", unidade: "ml" },                   // dose 0: fora
  ];
  const p = produtosParaEnvio(itens, { 2: "total" }, 4);
  assert.deepEqual(p, [
    { produto: "Cepravin", via: "Intramamária", quantidade: 1, unidade: "unidade" },
    { produto: "Vit E", via: undefined, quantidade: 10, unidade: "ml" },
  ]);
  // com uma vaca só, "total" não divide
  assert.equal(produtosParaEnvio(itens, { 2: "total" }, 1)[1].quantidade, 40);
});
test("total que baixa do estoque: por vaca multiplica, total vale como está", () => {
  assert.equal(totalAplicado(1, "por_vaca", 4), 4);
  assert.equal(totalAplicado(1, undefined, 0), 1);
  assert.equal(totalAplicado(40, "total", 4), 40);
});
test("data futura nunca baixa estoque", () => {
  assert.equal(aplicadoEfetivo(true, "2026-10-17", "2026-10-17"), true);
  assert.equal(aplicadoEfetivo(true, "2026-10-18", "2026-10-17"), false);
  assert.equal(aplicadoEfetivo(false, "2026-10-10", "2026-10-17"), false);
});
test("o que falta para salvar a secagem: vaca, motivo, vacina", () => {
  const ok = { nVacas: 2, motivo: "rotina", vacinaSim: false, vacinas: [] as string[] };
  assert.equal(erroDeSecagem(ok), null);
  assert.match(erroDeSecagem({ ...ok, nVacas: 0 }) ?? "", /ao menos uma vaca/);
  assert.match(erroDeSecagem({ ...ok, motivo: "" }) ?? "", /motivo/);
  assert.match(erroDeSecagem({ ...ok, vacinaSim: true }) ?? "", /vacina pré-parto/);
  assert.equal(erroDeSecagem({ ...ok, vacinaSim: true, vacinas: ["Rotavec"] }), null);
  // escore: em branco vale; de 1 a 5 vale; fora disso o servidor recusaria (400)
  assert.equal(erroDeSecagem({ ...ok, ecc: "" }), null);
  assert.equal(erroDeSecagem({ ...ok, ecc: "3,25" }), null);
  assert.match(erroDeSecagem({ ...ok, ecc: "6" }) ?? "", /escore/);
  assert.match(erroDeSecagem({ ...ok, ecc: "0.5" }) ?? "", /escore/);
});

test("mensagem do erro: a do Error quando existe, senão o texto padrão", () => {
  assert.equal(mensagemDoErro(new Error("Vaca 14 sem lactação"), "Erro"), "Vaca 14 sem lactação");
  assert.equal(mensagemDoErro(new Error(""), "Erro"), "Erro");
  assert.equal(mensagemDoErro("texto solto", "Erro"), "Erro");
  assert.equal(mensagemDoErro(undefined, "Erro"), "Erro");
});
