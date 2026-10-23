// Ida e volta do Sanitário Preventivo v2: o que o front ENVIA tem que caber
// nos schemas do back (todos com extra="forbid" — campo a mais = 422) e o que
// o GET devolve tem que voltar igual quando reenviado. Este teste lê o
// schemas.py de verdade, então mudar um campo no back sem mudar aqui quebra.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  AO_FECHAR, CAMPOS_ATESTADO, CAMPOS_CARENCIA_DECISAO, CAMPOS_CATALOGO_EXTRA, CAMPOS_COMPROVACAO, CAMPOS_CONSENTIMENTO,
  CAMPOS_DEFINICAO, CAMPOS_DIA_CRIAR, CAMPOS_DIA_EDITAR, CAMPOS_LANCAMENTO, CAMPOS_LEITURA, CAMPOS_PARAMETROS, CAMPOS_PRODUTO,
  CAMPOS_REGISTRO, CAMPOS_SERIE, CAMPOS_VETERINARIO, COLUNAS_FICHA, CONDICOES, DOSE_UNIDADES, EVENTO_TIPOS, MODOS_LEITE,
  PERIODO_MODOS, PRODUTO_MODOS, RESULTADOS, TIPOS_CAIXA,
  codigoDoDetalhe, definicaoCompleta, definicaoParaEnvio, definicaoVazia, diaCriarParaEnvio, diaEditarParaEnvio, diaSemana,
  diferencaDias, errosDoDetalhe, fmtData, hojeISO, lancamentoParaEnvio, numOuNulo, parametrosParaEnvio, produtoParaEnvio,
  registroParaEnvio, somarDias, textoDose, tipoDoDia, veterinarioParaEnvio,
} from "./sanitarioTipos.ts";

// ── leitura do schemas.py / definicao.py ──
const SCHEMAS = readFileSync(new URL("../../backend/fazenda/api/routers/sanitario/schemas.py", import.meta.url), "utf8");
const DEFINICAO_PY = readFileSync(new URL("../../backend/fazenda/rules/sanitario/definicao.py", import.meta.url), "utf8");

function classes(src: string): Map<string, string[]> {
  const out = new Map<string, string[]>();
  const pais = new Map<string, string>();
  let atual: string | null = null;
  for (const linha of src.split("\n")) {
    const c = /^class (\w+)\((\w+)\):/.exec(linha);
    if (c) { atual = c[1]; out.set(atual, []); pais.set(atual, c[2]); continue; }
    if (/^\S/.test(linha)) { atual = null; continue; }
    const f = /^    (\w+): /.exec(linha);
    if (atual && f && f[1] !== "model_config") out.get(atual)!.push(f[1]);
  }
  // herança (ex.: CatalogoDefinicaoIn(CaixaDefinicaoIn), RegistroSyncIn(RegistroIn))
  const resolver = (nome: string): string[] => {
    const pai = pais.get(nome);
    return [...(pai && out.has(pai) ? resolver(pai) : []), ...(out.get(nome) || [])];
  };
  const final = new Map<string, string[]>();
  for (const k of out.keys()) final.set(k, resolver(k));
  return final;
}
function literais(src: string): Map<string, string[]> {
  const out = new Map<string, string[]>();
  const re = /^(\w+) = Literal\[([\s\S]*?)\]/gm;
  for (const m of src.matchAll(re)) out.set(m[1], [...m[2].matchAll(/"([^"]+)"/g)].map((x) => x[1]));
  return out;
}
function tupla(src: string, nome: string): string[] {
  const m = new RegExp(`^${nome} = \\(([\\s\\S]*?)\\)`, "m").exec(src);
  assert.ok(m, `${nome} não encontrado em definicao.py`);
  return [...m[1].matchAll(/"([^"]+)"/g)].map((x) => x[1]);
}
const C = classes(SCHEMAS);
const L = literais(SCHEMAS);
const campos = (nome: string) => { const c = C.get(nome); assert.ok(c, `classe ${nome} não encontrada no schemas.py`); return c; };
const mesmoConjunto = (a: readonly string[], b: readonly string[], msg: string) => assert.deepEqual([...a].sort(), [...b].sort(), msg);
const subconjunto = (chaves: string[], permitidas: readonly string[], msg: string) => {
  const sobra = chaves.filter((k) => !permitidas.includes(k));
  assert.deepEqual(sobra, [], `${msg}: campos que o back recusaria (422): ${sobra.join(", ")}`);
};

test("listas de campos do front = campos dos schemas do back (extra=forbid)", () => {
  mesmoConjunto(CAMPOS_DEFINICAO, campos("CaixaDefinicaoIn"), "CaixaDefinicaoIn");
  mesmoConjunto([...CAMPOS_DEFINICAO, ...CAMPOS_CATALOGO_EXTRA], campos("CatalogoDefinicaoIn"), "CatalogoDefinicaoIn");
  mesmoConjunto(CAMPOS_ATESTADO, campos("AtestadoIn"), "AtestadoIn");
  mesmoConjunto(CAMPOS_COMPROVACAO, campos("ComprovacaoIn"), "ComprovacaoIn");
  mesmoConjunto(CAMPOS_LEITURA, campos("LeituraIn"), "LeituraIn");
  mesmoConjunto(CAMPOS_SERIE, campos("SerieDoseIn"), "SerieDoseIn");
  mesmoConjunto(CAMPOS_PRODUTO, campos("ProdutoIn"), "ProdutoIn");
  mesmoConjunto(CAMPOS_VETERINARIO, campos("VeterinarioIn"), "VeterinarioIn");
  mesmoConjunto(CAMPOS_CONSENTIMENTO, campos("ConsentimentoIn"), "ConsentimentoIn");
  mesmoConjunto(CAMPOS_DIA_CRIAR, campos("DiaCriarIn"), "DiaCriarIn");
  mesmoConjunto(CAMPOS_DIA_EDITAR, campos("DiaEditarIn"), "DiaEditarIn");
  mesmoConjunto(CAMPOS_REGISTRO, campos("RegistroIn"), "RegistroIn");
  mesmoConjunto(CAMPOS_LANCAMENTO, campos("LancamentoSimplesIn"), "LancamentoSimplesIn");
  mesmoConjunto(CAMPOS_PARAMETROS, campos("ParametrosIn"), "ParametrosIn");
  mesmoConjunto(CAMPOS_CARENCIA_DECISAO, campos("CarenciaDecisaoIn"), "CarenciaDecisaoIn");
});

test("vocabulário fechado do front = Literal do back", () => {
  const pares: [string, readonly string[]][] = [
    ["TipoCaixa", TIPOS_CAIXA], ["ProdutoModo", PRODUTO_MODOS], ["DoseUnidade", DOSE_UNIDADES], ["EventoTipo", EVENTO_TIPOS],
    ["PeriodoModo", PERIODO_MODOS], ["AoFechar", AO_FECHAR], ["Condicao", CONDICOES], ["ModoLeite", MODOS_LEITE],
    ["Resultado", RESULTADOS], ["ColunaFicha", COLUNAS_FICHA],
  ];
  for (const [nome, ts] of pares) {
    const py = L.get(nome);
    assert.ok(py, `Literal ${nome} não encontrado`);
    mesmoConjunto(ts, py, nome);
  }
});

test("o GET da caixa (CAMPOS_CAIXA + CAMPOS_VERSAO + categorias) cabe inteiro no PUT", () => {
  const doGet = [...tupla(DEFINICAO_PY, "CAMPOS_CAIXA"), ...tupla(DEFINICAO_PY, "CAMPOS_VERSAO"), "categorias"];
  subconjunto(doGet, campos("CaixaDefinicaoIn"), "definição devolvida pelo GET");
});

test("ida e volta da definição: o que o GET devolve, reenviado, sai igual", () => {
  const doGet = {
    ...definicaoVazia("vacina"), nome: "Brucelose B19", nome_curto: "B19", obrigatoria: true,
    produto_modo: "estoque", estoque_id: 12, dose_valor: 2, dose_unidade: "mL",
    pub_sexo: "F", categorias: [3, 4], pub_idade_min_dias: 120, pub_idade_max_dias: 240, pub_condicoes: ["prenhe"],
    jan_usa_evento: true, evento_tipo: "idade", evento_de_dias: 120, evento_ate_dias: 240, jan_usa_periodo: false,
    periodo_modo: null, periodo_grupos: [], comecar_em: "2027-01-01", serie: [{ dose: 2, apos_dias: 30, janela_dias: 30 }],
    legal_crmv_pedir: true, legal_atestado: { destinatario_tipo: "orgao", destinatario_texto: "SIDAGO", quando: "primeiro", dias: 30 },
    legal_comprovacao: { dias: 180, aviso_dias: 30, push: true, email: false }, legal_marca_texto: "algarismo do ano",
    car_leite_dias: 0, car_carne_dias: 21, car_modo_leite: "tanque",
  } as const;
  const enviado = definicaoParaEnvio(definicaoCompleta(doGet as never) as never);
  subconjunto(Object.keys(enviado), campos("CaixaDefinicaoIn"), "definicaoParaEnvio");
  for (const [k, v] of Object.entries(doGet)) assert.deepEqual(enviado[k], v, `campo ${k} mudou na ida e volta`);
});

test("definição: descarta campos que o back não conhece e normaliza números", () => {
  const d = definicaoParaEnvio({
    ...definicaoVazia(), id: 9, versao_numero: 3, categorias_ref: ["bezerr"], nome: "  Raiva ", dose_valor: "2,5" as unknown as number,
    estoque_id: "" as unknown as number, aglo_min: "" as unknown as number, car_leite_dias: "" as unknown as number,
    legal_atestado: { quando: "nfe", dias: 10, lixo: true } as never, pub_hist_tipo: null, pub_hist_caixa_id: 5,
  } as never);
  subconjunto(Object.keys(d), campos("CaixaDefinicaoIn"), "definição da fazenda");
  assert.equal("categorias_ref" in d, false, "categorias_ref é só do catálogo");
  assert.equal(d.nome, "Raiva");
  assert.equal(d.dose_valor, 2.5);
  assert.equal(d.estoque_id, null);
  assert.equal("aglo_min" in d, false, "aglo_min vazio cai no padrão do back (não manda null para campo int)");
  assert.equal(d.car_leite_dias, null, "carência em branco = não informada (null), nunca zero");
  assert.deepEqual(d.legal_atestado, { quando: "nfe", dias: 10 });
  assert.equal(d.pub_hist_caixa_id, null, "sem já/nunca recebeu, a vacina de referência vai vazia");
  const cat = definicaoParaEnvio({ ...definicaoVazia(), categorias_ref: ["bezerr"], pub_hist_catalogo_chave: "b19" } as never, { catalogo: true });
  subconjunto(Object.keys(cat), campos("CatalogoDefinicaoIn"), "definição do catálogo");
  assert.deepEqual(cat.categorias_ref, ["bezerr"]);
});

test("marcar o dia: corpo cabe no DiaCriarIn, produtos por id e veterinário", () => {
  const corpo = diaCriarParaEnvio({
    caixa_ids: [1, 2], data: "2026-10-23", hora: " ", data_prevista: "2026-10-23",
    veterinario: { pessoa_id: "7" as unknown as number, texto: "", crmv: "" },
    produtos: { 1: { modo: "estoque", estoque_id: 3, dose_valor: 2, dose_unidade: "mL", extra: 1 } as never, 2: {} },
    itens: [{ animal_id: 10, caixa_ids: [1], numero: "0701" } as never], consentimentos: [{ animal_id: 10, caixa_id: 1, aceito: true, motivo_exibido: "macho" }],
    decisao_riscos: { decisao: "manter", texto: "riscos" }, observacao: "",
  });
  subconjunto(Object.keys(corpo), campos("DiaCriarIn"), "DiaCriarIn");
  assert.deepEqual(corpo.veterinario, { pessoa_id: 7 });
  assert.equal(corpo.hora, null);
  assert.equal(corpo.observacao, null);
  assert.deepEqual(Object.keys(corpo.produtos as object), ["1"], "produto vazio não vai");
  subconjunto(Object.keys((corpo.produtos as Record<string, object>)["1"]), campos("ProdutoIn"), "ProdutoIn");
  subconjunto(Object.keys((corpo.itens as object[])[0]), campos("DiaItemIn"), "DiaItemIn");
  subconjunto(Object.keys((corpo.consentimentos as object[])[0]), campos("ConsentimentoIn"), "ConsentimentoIn");
  subconjunto(Object.keys(corpo.decisao_riscos as object), campos("DecisaoRiscosIn"), "DecisaoRiscosIn");
  const ed = diaEditarParaEnvio({ versao_lock: 2, data: "2026-10-24", veterinario: { texto: "Dr. Paulo", crmv: "GO 1" } });
  subconjunto(Object.keys(ed), campos("DiaEditarIn"), "DiaEditarIn");
  assert.deepEqual(ed.veterinario, { texto: "Dr. Paulo", crmv: "GO 1" });
  assert.equal(veterinarioParaEnvio({ pessoa_id: null, texto: " ", crmv: "" }), null);
});

test("registro e lançamento simples: só campos do schema, aninhados inclusive", () => {
  const r = registroParaEnvio({
    animal_id: 1, caixa_id: 2, produto: { modo: "sem_estoque", texto: " Frasco ", dose_valor: "1,5" as unknown as number },
    consentimento: { aceito: true, motivo_exibido: "fora", quer_atestado: false, lixo: 1 } as never,
    carencia: { modo: "descarte", leite_dias: "7" as unknown as number, carne_dias: null }, peso_kg: "320" as unknown as number,
  });
  subconjunto(Object.keys(r), campos("RegistroIn"), "RegistroIn");
  subconjunto(Object.keys(r.consentimento as object), campos("ConsentimentoRegistroIn"), "ConsentimentoRegistroIn");
  subconjunto(Object.keys(r.carencia as object), campos("CarenciaDecisaoIn"), "CarenciaDecisaoIn");
  assert.deepEqual(r.produto, { modo: "sem_estoque", texto: "Frasco", dose_valor: 1.5 });
  assert.deepEqual(r.carencia, { modo: "descarte", leite_dias: 7, carne_dias: null });
  assert.equal(r.peso_kg, 320);

  const l = lancamentoParaEnvio({
    caixa_id: null, outro_texto: " carbúnculo ", data: "2026-10-01", retroativo_motivo: "", animal_ids: [3, 4],
    numeros: ["2501", " ", "2502"], atestado: { numero: "", destinatario: " " }, carencia: { leite_dias: 0, carne_dias: 0 },
    resultados: {}, consentimentos: [], chave_lote: "lanc:1",
  });
  subconjunto(Object.keys(l), campos("LancamentoSimplesIn"), "LancamentoSimplesIn");
  assert.equal(l.outro_texto, "carbúnculo");
  assert.equal(l.retroativo_motivo, null);
  assert.deepEqual(l.numeros, ["2501", "2502"]);
  assert.equal(l.atestado, null, "atestado em branco não vai");
  assert.deepEqual(l.carencia, { leite_dias: 0, carne_dias: 0 }, "“não tem carência” = zero dias de verdade");

  const p = parametrosParaEnvio({ uf: " go ", antecedencia_padrao_dias: "30" as unknown as number, atualizado_em: "x" } as never);
  subconjunto(Object.keys(p), campos("ParametrosIn"), "ParametrosIn");
  assert.equal(p.uf, "GO");
  assert.equal(p.antecedencia_padrao_dias, 30);
  assert.equal(produtoParaEnvio(null), null);
});

test("datas no fuso de São Paulo, sem new Date('AAAA-MM-DD')", () => {
  // 02:00 UTC de 22/10 ainda é 21/10 em São Paulo (UTC−3)
  assert.equal(hojeISO(new Date(Date.UTC(2026, 9, 22, 2, 0))), "2026-10-21");
  assert.equal(hojeISO(new Date(Date.UTC(2026, 9, 22, 4, 0))), "2026-10-22");
  assert.equal(fmtData("2026-10-21"), "21/10/2026");
  assert.equal(fmtData("2026-10-21", true), "21/10");
  assert.equal(fmtData(null), "—");
  assert.equal(somarDias("2026-10-30", 3), "2026-11-02");
  assert.equal(somarDias("2026-03-01", -1), "2026-02-28");
  assert.equal(diaSemana("2026-10-21"), "qua");
  assert.equal(diferencaDias("2026-10-21", "2026-12-25"), 65);
});

test("leitura dos 409/422 e textos curtos", () => {
  assert.equal(codigoDoDetalhe({ codigo: "consentimento_necessario", itens: [] }), "consentimento_necessario");
  assert.equal(codigoDoDetalhe({ erro: "carencia_bloqueio", msg: "x" }), "carencia_bloqueio");
  assert.equal(codigoDoDetalhe("texto"), null);
  assert.deepEqual(errosDoDetalhe({ codigo: "validacao", erros: [{ etapa: 1, campo: "nome", mensagem: "m" }] }), [{ etapa: 1, campo: "nome", mensagem: "m" }]);
  assert.equal(numOuNulo(""), null);
  assert.equal(textoDose({ dose_valor: 1, dose_unidade: "mL_por_x_kg", dose_x_kg: 50 }), "1 mL por 50 kg");
  assert.equal(tipoDoDia([{ tipo: "exame" }, { tipo: "exame" }]), "Exame");
  assert.equal(tipoDoDia([{ tipo: "exame" }, { tipo: "vacina" }]), "Vacina");
});

test("ehItemFarmacia: só Farmácia entra na lista de estoque do preventivo", async () => {
  const { ehItemFarmacia } = await import("./sanitarioTipos.ts");
  assert.ok(ehItemFarmacia({ nome: "Boostin", finalidade: "Medicamento" }));
  assert.ok(!ehItemFarmacia({ nome: "Milho moído", finalidade: "Ração/Alimento" }));
  assert.ok(!ehItemFarmacia({ nome: "Vacina na caixa errada", finalidade: "Material/Insumo" }), "finalidade decide sozinha");
  assert.ok(ehItemFarmacia({ nome: "Ivomec", principio_ativo_id: 3 }));
  assert.ok(ehItemFarmacia({ nome: "X", classificacao_medicamento: "Vacina" }));
  assert.ok(ehItemFarmacia({ nome: "X", categoria_medicamento_ids: [2] }));
  assert.ok(ehItemFarmacia({ nome: "Aftosa", categoria: "Medicamentos e produtos veterinários" }));
  assert.ok(!ehItemFarmacia({ nome: "Silagem", categoria: "Ração e insumos alimentares" }));
  assert.ok(!ehItemFarmacia({ nome: "Sêmen — X", categoria: "Sêmen e genética" }));
  assert.ok(!ehItemFarmacia({ nome: "Núcleo", categoria_alimento_id: 4 }), "item ligado à Alimentação");
  assert.ok(ehItemFarmacia({ nome: "Vacina B19" }), "sem classificação, o nome diz que é vacina");
  assert.ok(ehItemFarmacia({ nome: "Vermífugo oral" }));
  assert.ok(!ehItemFarmacia({ nome: "Alimentação" }));
});
