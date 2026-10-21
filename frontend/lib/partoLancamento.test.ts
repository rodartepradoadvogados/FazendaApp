import { test } from "node:test";
import assert from "node:assert/strict";
import {
  abortosSemResposta, avisoFreemartin, delDesdeParto, chaveCria, classeColostro, classeEficiencia, classeSoro, colostroTemDado, colostroVazio,
  criasDaLinha, enriquecimento, erroSexo, erroSexo2, intervaloColostroHoras, linhaEfetiva, linhaVazia, payloadColostragem, payloadParto,
  problemasDeSalvar, relativoPrevisto, resumoDosPartos,
} from "./partoLancamento.ts";

const HOJE = "2026-10-17";
const l = (p: Partial<ReturnType<typeof linhaVazia>> = {}) => ({ ...linhaVazia(HOJE), ...p });

test("cria com número e sem sexo é erro (nunca assume fêmea)", () => {
  assert.equal(erroSexo(l({ cria: "4830" })), true);
  assert.equal(erroSexo(l({ cria: "4830", sexo: "M" })), false);
  assert.equal(erroSexo(l()), false); // sem número = sem cria
  assert.equal(erroSexo(l({ tipo: "Aborto", cria: "4830" })), false); // aborto não tem cria
});

test("2ª cria só exige sexo quando gemelar e com número", () => {
  assert.equal(erroSexo2(l({ gemelar: true, cria2: "4831" })), true);
  assert.equal(erroSexo2(l({ gemelar: true, cria2: "4831", sexo2: "F" })), false);
  assert.equal(erroSexo2(l({ gemelar: false, cria2: "4831" })), false);
  assert.equal(erroSexo2(l({ gemelar: true })), false);
});

test("payload do parto: sem cria => crias vazio; sexo vai como F/M e natimorto força nasceu_viva=false", () => {
  assert.deepEqual(payloadParto("10987", l({ tipo: "Normal" })).crias, []);
  const p = payloadParto("4412", l({ tipo: "Natimorto", cria: "4830", sexo: "M", gemelar: true, cria2: "4831", sexo2: "F", gemSexo: "FM", placenta: true }));
  assert.deepEqual(p.crias, [
    { numero: "4830", sexo: "M", nasceu_viva: false },
    { numero: "4831", sexo: "F", nasceu_viva: false },
  ]);
  assert.equal(p.gemelar, true);
  assert.equal(p.gemelar_sexo, "FM");
  assert.equal(p.retencao_placenta, true);
  assert.equal(p.tipo_parto, "Natimorto");
});

test("tipo vazio vira undefined; gemelar_sexo vazio vira undefined (o servidor deriva dos sexos)", () => {
  const p = payloadParto("1", l({ cria: "9", sexo: "F", gemelar: true, cria2: "10", sexo2: "M" }));
  assert.equal(p.tipo_parto, undefined);
  assert.equal(p.gemelar_sexo, undefined);
});

test("aborto não envia cria nem em linha preenchida", () => {
  assert.deepEqual(criasDaLinha(l({ tipo: "Aborto", cria: "4830", sexo: "F" })), []);
});

test("cria baixada manual => nasceu_viva=false só nela", () => {
  const c = criasDaLinha(l({ cria: "1", sexo: "F", baixada: true, gemelar: true, cria2: "2", sexo2: "M" }));
  assert.deepEqual(c.map((x) => x.nasceu_viva), [false, true]);
});

test("modo Lote: data e tipo vêm do topo, sem gêmeos nem resposta de aborto", () => {
  const e = linhaEfetiva(l({ gemelar: true, cria2: "9", tipo: "Aborto", lact: "sim", data: "2026-01-01" }), true, HOJE, "Normal");
  assert.equal(e.data, HOJE); assert.equal(e.tipo, "Normal"); assert.equal(e.gemelar, false); assert.equal(e.cria2, ""); assert.equal(e.lact, "");
  const intacta = l({ tipo: "Cesariana" });
  assert.equal(linhaEfetiva(intacta, false, HOJE, "Normal"), intacta);
});

test("problemas de salvar: sexo faltando, data vazia e número de cria repetido", () => {
  const efs = [
    { n: "A", l: l({ cria: "100" }) },
    { n: "B", l: l({ cria: "100", sexo: "F", data: "" }) },
    { n: "C", l: l({ cria: "200", sexo: "M" }) },
  ];
  const p = problemasDeSalvar(efs);
  assert.deepEqual(p.semSexo, ["A"]);
  assert.deepEqual(p.semData, ["B"]);
  assert.deepEqual(p.repetidas, ["100"]);
});

test("resumo: aborto não conta como parto nem como cria", () => {
  const r = resumoDosPartos([
    { n: "1", l: l({ cria: "9", sexo: "F", gemelar: true, cria2: "10", sexo2: "M" }) },
    { n: "2", l: l({ tipo: "Aborto" }) },
    { n: "3", l: l() },
  ]);
  assert.deepEqual(r, { registros: 3, abortos: 1, partos: 2, crias: 2 });
});

test("abortos sem resposta ao 'abrir lactação?'", () => {
  const efs = [{ n: "1", l: l({ tipo: "Aborto" }) }, { n: "2", l: l({ tipo: "Aborto", lact: "nao" }) }, { n: "3", l: l() }];
  assert.deepEqual(abortosSemResposta(efs), ["1"]);
});

test("freemartin: FM informado ou sexos diferentes", () => {
  assert.equal(avisoFreemartin(l({ gemelar: true, gemSexo: "FM" })), true);
  assert.equal(avisoFreemartin(l({ gemelar: true, sexo: "F", sexo2: "M" })), true);
  assert.equal(avisoFreemartin(l({ gemelar: true, sexo: "F", sexo2: "F" })), false);
  assert.equal(avisoFreemartin(l({ gemelar: false, gemSexo: "FM" })), false);
});

test("colostro: 'Enriquecer até' sozinho não conta como dado informado", () => {
  assert.equal(colostroTemDado(colostroVazio()), false);
  assert.equal(colostroTemDado(undefined), false);
  assert.equal(colostroTemDado({ ...colostroVazio(), enriq: "28" }), false);
  assert.equal(colostroTemDado({ ...colostroVazio(), po: true }), true);
  assert.equal(colostroTemDado({ ...colostroVazio(), litros: "4" }), true);
});

test("payload da colostragem: mesmos campos de sempre, por cria, aceita vírgula decimal", () => {
  const p = payloadColostragem("4830", {
    ...colostroVazio(), horaParto: "05:40", horaColostro: "06:25", peso: "38,5", tomou: "Sim", litros: "4", brix: "22", soro: "8.5", prot: "6,0", po: true,
  }, HOJE);
  assert.deepEqual(p, {
    numero_animal: "4830", tomou_colostro: true, litros_colostro: 4, brix_colostro: 22, data_colostro: HOJE,
    hora_parto: "05:40", hora_colostro: "06:25", peso_nascer_kg: 38.5, brix_soro: 8.5, proteina_serica: 6,
    apenas_colostro_po: true, data_teste_sangue: HOJE,
  });
  const so = payloadColostragem("1", { ...colostroVazio(), tomou: "Não" }, HOJE);
  assert.equal(so.tomou_colostro, false);
  assert.equal(so.data_colostro, undefined);
  assert.equal(so.data_teste_sangue, undefined);
  assert.equal(so.apenas_colostro_po, undefined);
});

test("chave do colostro é por cria (mãe|1 e mãe|2 não se misturam)", () => {
  assert.notEqual(chaveCria("4412", 1), chaveCria("4412", 2));
});

test("classificações do manual: ouro/prata/bronze, soro e eficiência", () => {
  assert.equal(classeColostro(26).tom, "ok"); assert.equal(classeColostro(25).tom, "atencao");
  assert.equal(classeColostro(18).tom, "atencao"); assert.equal(classeColostro(17).tom, "bloqueio");
  assert.equal(classeSoro(8.4).tom, "ok"); assert.equal(classeSoro(8.1).tom, "atencao"); assert.equal(classeSoro(8).tom, "bloqueio");
  assert.equal(classeEficiencia(9.5, null)?.txt, "Excelente");
  assert.equal(classeEficiencia(8.0, 6.5)?.tom, "bloqueio"); // Brix tem prioridade sobre a proteína
  assert.equal(classeEficiencia(null, 5.9)?.txt, "Boa");
  assert.equal(classeEficiencia(null, null), null);
});

test("intervalo parto→colostro trata a virada de dia", () => {
  assert.equal(intervaloColostroHoras("05:40", "06:25"), 0.75);
  assert.equal(intervaloColostroHoras("23:30", "00:30"), 1);
  assert.equal(intervaloColostroHoras("", "06:00"), null);
});

test("enriquecimento: medidas por litro e total em gramas", () => {
  assert.deepEqual(enriquecimento(22, 25, 4), { porLitro: 3, total: 12, gramas: 180 });
  assert.equal(enriquecimento(26, 25, 4), null);
  assert.equal(enriquecimento(null, 25, 4), null);
});

test("relativo da data prevista", () => {
  assert.equal(relativoPrevisto("2026-10-17", HOJE), "hoje");
  assert.equal(relativoPrevisto("2026-10-16", HOJE), "ontem");
  assert.equal(relativoPrevisto("2026-10-18", HOJE), "amanhã");
  assert.equal(relativoPrevisto("2026-10-14", HOJE), "3 d atrás");
  assert.equal(relativoPrevisto("2026-10-21", HOJE), "em 4 d");
});

test("DEL da mãe conta os dias desde a data do parto (retroativo não é DEL 0) e nunca fica negativo", () => {
  assert.equal(delDesdeParto("2026-10-17", "2026-10-17"), 0);
  assert.equal(delDesdeParto("2026-10-19", "2026-10-21"), 2);
  assert.equal(delDesdeParto("2026-09-30", "2026-10-02"), 2);
  assert.equal(delDesdeParto("2026-10-25", "2026-10-21"), 0);
  assert.equal(delDesdeParto("", "2026-10-21"), 0);
});
