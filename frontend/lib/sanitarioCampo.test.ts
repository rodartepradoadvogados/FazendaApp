// App de campo do sanitário: o que o celular manda pela fila cabe nos schemas
// do back (extra="forbid"), a resposta por registro vira a ação certa na fila
// e as contas do curral (pendentes, peso estimado, dose) batem.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  CAMPOS_CIENCIA, CAMPOS_HEARTBEAT, CAMPOS_REGISTRO_SYNC, corpoCiencia, CAMPOS_SINCRONIZAR, alvosPendentes, chaveAC, corpoHeartbeat, corpoSincronizar,
  decidirItem, filaAtrasada, foraDaRegra, interpretarSync, itensPreparacao, juntarResultados, pesoMedioCategoria, pesoParaDose,
  quantidadeDose, registrosDoLancamento, type CorpoSan, type ResultadoSan,
} from "./sanitarioCampo.ts";
import type { PacoteOffline, SincronizarOut } from "./sanitarioTipos.ts";

const SCHEMAS = readFileSync(new URL("../../backend/fazenda/api/routers/sanitario/schemas.py", import.meta.url), "utf8");

function campos(classe: string): string[] {
  const linhas = SCHEMAS.split("\n");
  const ini = linhas.findIndex((l) => l.startsWith(`class ${classe}(`));
  assert.ok(ini >= 0, `classe ${classe} não encontrada no schemas.py`);
  const pai = /class \w+\((\w+)\)/.exec(linhas[ini])![1];
  const out: string[] = pai !== "Esquema" && pai !== "BaseModel" ? campos(pai) : [];
  for (let i = ini + 1; i < linhas.length && !/^\S/.test(linhas[i]); i++) {
    const m = /^    (\w+): /.exec(linhas[i]);
    if (m && m[1] !== "model_config") out.push(m[1]);
  }
  return out;
}

test("registro da fila = RegistroSyncIn; sincronizar e heartbeat batem com o back", () => {
  assert.deepEqual([...CAMPOS_REGISTRO_SYNC].sort(), campos("RegistroSyncIn").sort());
  assert.deepEqual([...CAMPOS_SINCRONIZAR].sort(), campos("SincronizarIn").sort());
  assert.deepEqual([...CAMPOS_HEARTBEAT].sort(), campos("HeartbeatIn").sort());
  assert.deepEqual([...CAMPOS_CIENCIA].sort(), campos("CienciaPreparacaoIn").sort());
  const corpo = corpoSincronizar("uid-1", "Celular do Zé", [{
    chave_idempotencia: "k1", dia_id: 7, animal_id: 3, caixa_id: 2, data: "2026-10-21", hora: "07:40",
    produto: { modo: "estoque", estoque_id: 5, dose_valor: 2, dose_unidade: "mL" }, peso_kg: null,
    // campos estranhos não podem vazar (extra="forbid")
    ...({ lixo: 1 } as object),
  }], 3);
  assert.deepEqual(Object.keys(corpo).sort(), [...CAMPOS_SINCRONIZAR].sort());
  const reg = (corpo.registros as Record<string, unknown>[])[0];
  for (const k of Object.keys(reg)) assert.ok((CAMPOS_REGISTRO_SYNC as readonly string[]).includes(k), `campo ${k} não existe no back`);
  assert.equal(reg.dia_id, 7);
  assert.equal(reg.outro_texto, null);
  const hb = corpoHeartbeat("uid-1", null, 0, "2026-10-20T10:00:00Z");
  assert.deepEqual(Object.keys(hb).sort(), [...CAMPOS_HEARTBEAT].sort());
  assert.equal(hb.fila_mais_antigo_em, null, "sem pendentes não informa o mais antigo");
});

function corpo(chave: string, extra: Partial<CorpoSan> = {}): CorpoSan {
  return { v: 1, registro: { chave_idempotencia: chave, dia_id: 1, animal_id: 10, caixa_id: 2 }, numero: "2401", caixa: "B19",
    dia_nome: "Vacina · B19", estado: "fila", ...extra };
}

test("resposta por registro: gravado/duplicado/conflito saem da fila; pendente e erro ficam com o motivo", () => {
  const resp: SincronizarOut = {
    dispositivo_id: 1, gravados: 1, duplicados: 1, pendentes: 1, conflitos: 1, erros: 1,
    itens: [
      { indice: 0, status: "gravado", registro_id: 50, animal_id: 10, numero: "2401", caixa_id: 2, requer: [],
        avisos: [{ codigo: "peso_estimado", texto: "2401: sem pesagem; usado o peso médio." }] },
      { indice: 1, status: "duplicado", registro_id: 51, animal_id: 10, numero: "2401", caixa_id: 2, requer: [], avisos: [] },
      { indice: 2, status: "conflito", registro_id: 52, animal_id: 10, numero: "2401", caixa_id: 2, requer: [], avisos: [],
        conflito_log_id: 99 },
      { indice: 3, status: "pendente", registro_id: null, animal_id: 10, numero: "2401", caixa_id: 2, requer: ["consentimento"],
        avisos: [], motivo_fora: "macho", pergunta_atestado: true },
      { indice: 4, status: "erro", registro_id: null, animal_id: null, numero: "x", caixa_id: 2, requer: [],
        avisos: [{ codigo: "animal_inexistente", texto: "Animal não encontrado nesta fazenda." }] },
    ],
  };
  const env = ["a", "b", "c", "d", "e"].map((k) => ({ id: k, corpo: corpo(k) }));
  const { acoes, resultados } = interpretarSync(env, resp, "2026-10-21T10:00:00Z");
  assert.deepEqual(acoes.map((a) => a.tipo), ["remover", "remover", "remover", "atualizar", "atualizar"]);
  const pend = acoes[3];
  assert.ok(pend.tipo === "atualizar" && pend.corpo.estado === "requer" && pend.corpo.requer?.includes("consentimento"));
  assert.ok(pend.tipo === "atualizar" && pend.corpo.pergunta_atestado === true);
  const err = acoes[4];
  assert.ok(err.tipo === "atualizar" && err.corpo.estado === "erro" && /não encontrado/.test(err.erro || ""));
  assert.equal(resultados[0].registro_id, 50);
  assert.match(resultados[0].texto, /peso médio/);
  assert.equal(resultados[2].conflito_log_id, 99);
  // decidir reabre para a fila com o consentimento no registro
  const reaberto = decidirItem((pend as { corpo: CorpoSan }).corpo, { consentimento: { aceito: true, motivo_exibido: "macho" } });
  assert.equal(reaberto.estado, "fila");
  assert.equal(reaberto.registro.consentimento?.aceito, true);
});

test("juntar resultados: mais novo primeiro, sem repetir chave", () => {
  const r = (chave: string, status: ResultadoSan["status"]): ResultadoSan => ({ chave, status, numero: "1", caixa: "x",
    dia_id: null, registro_id: null, conflito_log_id: null, texto: "", em: "" });
  const j = juntarResultados([r("a", "pendente"), r("b", "gravado")], [r("a", "gravado"), r("c", "erro")]);
  assert.deepEqual(j.map((x) => `${x.chave}:${x.status}`), ["c:erro", "a:gravado", "b:gravado"]);
});

test("aviso local de 24 h sem enviar", () => {
  const agora = Date.parse("2026-10-22T08:00:00Z");
  assert.equal(filaAtrasada("2026-10-21T07:40:00Z", agora, 24), true);
  assert.equal(filaAtrasada("2026-10-21T09:00:00Z", agora, 24), false);
  assert.equal(filaAtrasada(null, agora), false);
});

const PACOTE = {
  dia: { id: 1, itens: [
    { id: 1, animal_id: 10, numero: "2401", caixa_id: 2, origem: "janela", estado: "pendente", consentimento_log_id: null, registro_id: null },
    { id: 2, animal_id: 10, numero: "2401", caixa_id: 3, origem: "manual", estado: "pendente", consentimento_log_id: null, registro_id: null },
    { id: 3, animal_id: 11, numero: "2402", caixa_id: 2, origem: "janela", estado: "feito", consentimento_log_id: null, registro_id: 9 },
    { id: 4, animal_id: 12, numero: "2403", caixa_id: 2, origem: "janela", estado: "pendente", consentimento_log_id: null, registro_id: null },
  ], contagens: { animais: 3, pendentes: 3, feitos: 1, registros_apos_fechamento: 0 } },
  animais: [
    { animal_id: 10, brinco: "2401", categoria: "Bezerra", peso: null, caixas: { "2": { elegivel: true, motivo: null, kind: null } } },
    { animal_id: 12, brinco: "2403", categoria: "Bezerra", peso: 120, caixas: {} },
    { animal_id: 13, brinco: "2404", categoria: "Bezerra", peso: 140, caixas: { "2": { elegivel: false, motivo: "macho", kind: "sexo" } } },
  ],
} as unknown as PacoteOffline;

test("pendentes do tronco: itens do dia + incluídos no curral, sem feitos e sem 'não aplicar'", () => {
  let alvos = alvosPendentes(PACOTE, [], []);
  assert.deepEqual(alvos.map((a) => `${a.numero}:${a.caixas.join("+")}:${a.origem}`), ["2401:2+3:manual", "2403:2:janela"]);
  alvos = alvosPendentes(PACOTE, [{ animal_id: 13, numero: "2404", caixas: [2], consent: { "2": { aceito: true, motivo_exibido: "macho" } } },
    { animal_id: null, numero: "9999", caixas: [2], consent: {} }], [chaveAC("a:10", 2)], ["a:12"]);
  assert.deepEqual(alvos.map((a) => `${a.numero}:${a.caixas.join("+")}:${a.origem}`), ["2401:3:manual", "2404:2:curral", "9999:2:curral"]);
  assert.equal(alvos[2].semCadastro, true);
  assert.equal(alvos[1].consent["2"].aceito, true);
  assert.deepEqual(foraDaRegra(PACOTE.animais[2], [2]), [{ caixa_id: 2, motivo: "macho" }]);
});

test("peso estimado pela categoria e dose por peso", () => {
  assert.equal(pesoMedioCategoria(PACOTE.animais, "Bezerra"), 130);
  assert.deepEqual(pesoParaDose({ peso: null, categoria: "Bezerra" }, PACOTE.animais), { peso: 130, estimado: true });
  assert.deepEqual(pesoParaDose({ peso: 200, categoria: "Bezerra" }, PACOTE.animais), { peso: 200, estimado: false });
  assert.deepEqual(pesoParaDose({ peso: null, categoria: "Touro" }, PACOTE.animais), { peso: null, estimado: false });
  assert.equal(quantidadeDose({ dose_valor: 1, dose_unidade: "mL_por_x_kg", dose_x_kg: 50 }, 130), 2.6);
  assert.equal(quantidadeDose({ dose_valor: 0.2, dose_unidade: "mL_por_kg" }, 100), 20);
  assert.equal(quantidadeDose({ dose_valor: 2, dose_unidade: "mL" }, null), 2);
});

test("preparação: produto, material, CRMV e carência sem decisão", () => {
  const itens = itensPreparacao({
    dia: PACOTE.dia,
    estoques: [{ id: 5, nome: "B19 Ourofino", unidade: "dose", saldo: 0 }],
    caixas: [
      { caixa_id: 2, nome: "Brucelose B19", nome_curto: "B19", tipo: "vacina", produto: { modo: "estoque", estoque_id: 5, dose_valor: 2, dose_unidade: "mL" },
        regras: { legal_crmv_pedir: true, carencia_precisa_decisao: "Produto sem estoque: carência desconhecida." } },
      { caixa_id: 3, nome: "Tuberculina", nome_curto: "TB", tipo: "exame", produto: {}, regras: { legal_leitura: { horas: 72 } } },
    ],
  });
  const ids = itens.map((i) => i.id);
  assert.ok(ids.includes("produto:2") && ids.includes("exame:3") && ids.includes("crmv") && ids.includes("carencia:2") && ids.includes("material"));
  assert.match(itens.find((i) => i.id === "produto:2")!.detalhe || "", /sem saldo/);
  assert.match(itens.find((i) => i.id === "exame:3")!.detalhe || "", /72 h/);
});

test("lançamento simples sem sinal vira registros com a mesma chave do back", () => {
  const regs = registrosDoLancamento({
    caixa_id: 2, data: "2026-10-01", animal_ids: [10, 10, 11], numeros: ["777"], aplicador_texto: " Zé ",
    consentimentos: [{ animal_id: 11, caixa_id: 2, aceito: true, motivo_exibido: "macho" }], resultados: { 10: "negativo" },
  }, "lanc:abc");
  assert.deepEqual(regs.map((r) => r.chave_idempotencia), ["lanc:abc:10", "lanc:abc:11", "lanc:abc:n777"]);
  assert.equal(regs[0].resultado, "negativo");
  assert.equal(regs[1].consentimento?.aceito, true);
  assert.equal(regs[2].numero_animal, "777");
  assert.equal(regs[0].aplicador_texto, "Zé");
  assert.equal(regs[0].dia_id, null);
  const outro = registrosDoLancamento({ outro_texto: "Vermífugo da loja", data: "2026-10-21", animal_ids: [1] }, "k");
  assert.equal(outro[0].caixa_id, null);
  assert.equal(outro[0].outro_texto, "Vermífugo da loja");
  // retroativo: o motivo vai pela fila (RegistroSyncIn.retroativo_motivo)
  const retro = registrosDoLancamento({ caixa_id: 2, data: "2026-10-01", retroativo_motivo: " sem sinal ", animal_ids: [5] }, "r");
  assert.equal(retro[0].retroativo_motivo, "sem sinal");
  const env = corpoSincronizar("uid", null, retro, 0).registros as Record<string, unknown>[];
  assert.equal(env[0].retroativo_motivo, "sem sinal");
});

test("ciência da preparação: corpo bate com CienciaPreparacaoIn", () => {
  const c = corpoCiencia({ nome: " Zé ", em: "2026-10-21T10:00:00.000Z", itens: ["Seringas"] }, "uid-1");
  assert.deepEqual(Object.keys(c).sort(), [...CAMPOS_CIENCIA].sort());
  assert.equal(c.texto, "Zé");
  assert.deepEqual(c.itens_abertos, ["Seringas"]);
});
