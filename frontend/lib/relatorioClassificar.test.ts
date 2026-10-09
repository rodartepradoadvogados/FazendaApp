import { test } from "node:test";
import assert from "node:assert/strict";
import {
  ACAO_DO_MOTIVO, MOTIVOS, acoesDasSugestoes, acoesDoControle, agruparLinhas, destinoDaLinha, filtrarLinhas, fraseClassificar, limitarGrupos,
  mensagemAplicada, mensagemDesfeita, podeAplicar, sugestaoAplicavel, textoDoLote, tipoUniforme, totais,
} from "./relatorioClassificar.ts";
import type { FilaClassificacao, LinhaPendencia, ResultadoLote, ResultadoReversao } from "./classificacaoApi.ts";

const brl = (v: number) => `R$ ${v.toFixed(2).replace(".", ",")}`;
let seq = 0;
const linha = (o: Partial<LinhaPendencia> = {}): LinhaPendencia => ({
  chave: `k${++seq}`, motivo: "conta_sem_linha_dre", numero_lancamento: `LC-${seq}`, conta_id: seq, item_id: seq + 100,
  tipo: "despesa", valor: 100, parcelas: 1, data: "2031-03-12", pago: false, fornecedor: "AUD-Silo", descricao: "Silagem", produto: "Silagem",
  centro_custo: "Pecuária Leiteira", codigo_conta: "8.20", nome_conta: "AUD Silagem comprada", conta_no_plano: true, natureza_atual: null,
  origem_automatica: null, mes_fechado: false, meses_fechados: [], acoes: { conta: true, linha_dre: true, natureza: true }, travas: {},
  sugestao: null, ...o,
});

test("cada motivo tem uma ação própria, na ordem do servidor", () => {
  assert.deepEqual(MOTIVOS, ["conta_sem_linha_dre", "sem_codigo_conta", "item_sem_conta_automatica", "natureza_nao_informada"]);
  assert.deepEqual(MOTIVOS.map((m) => ACAO_DO_MOTIVO[m]), ["linha_dre", "conta", "conta", "natureza"]);
});

test("agrupar: motivo da conta junta por conta com total; os outros ficam num bloco só", () => {
  const ls = [linha({ valor: 700 }), linha({ valor: 300 }), linha({ codigo_conta: "9.1", nome_conta: "Energia", valor: 80 }),
    linha({ codigo_conta: "9.1", tipo: "receita", valor: 5 })];
  const g = agruparLinhas(ls, "conta_sem_linha_dre");
  assert.deepEqual(g.map((x) => [x.codigo, x.linhas.length, x.totalDespesa, x.totalReceita]), [["8.20", 2, 1000, 0], ["9.1", 2, 80, 5]]);
  const plano = agruparLinhas(ls, "sem_codigo_conta");
  assert.equal(plano.length, 1);
  assert.equal(plano[0].codigo, null);
  assert.equal(plano[0].linhas.length, 4);
});

test("limitar: corta nas primeiras N linhas, mas o grupo guarda a quantidade e o total inteiros", () => {
  const ls = [linha({ valor: 1 }), linha({ valor: 2 }), linha({ valor: 3 }), linha({ codigo_conta: "9.1", valor: 4 })];
  const g = limitarGrupos(agruparLinhas(ls, "conta_sem_linha_dre"), 2);
  assert.deepEqual(g.map((x) => [x.codigo, x.linhas.length, x.quantidade, x.totalDespesa]), [["8.20", 2, 3, 6]]);
  assert.equal(limitarGrupos(agruparLinhas(ls, "conta_sem_linha_dre"), 4).length, 2);
  assert.equal(limitarGrupos([], 5).length, 0);
});

test("agrupar guarda a sugestão da conta (só a da conta, nunca a de um lançamento)", () => {
  const sug = { tipo: "linha_dre" as const, alvo: { codigo: "8.20" }, valor: "CUSTO_VARIAVEL", rotulo: "Linha da DRE: Custo variável (CPV/CMV)", motivo: "x" };
  const g = agruparLinhas([linha({ sugestao: sug })], "conta_sem_linha_dre");
  assert.equal(g[0].sugestao?.valor, "CUSTO_VARIAVEL");
  const g2 = agruparLinhas([linha({ sugestao: { ...sug, tipo: "conta" } })], "conta_sem_linha_dre");
  assert.equal(g2[0].sugestao, null);
});

test("filtrar por texto (sem acento) e por conta (a conta e as filhas)", () => {
  const ls = [linha({ fornecedor: "Cooperativa São João" }), linha({ fornecedor: "Posto Mil", codigo_conta: "3.04.01", nome_conta: "Diesel" }), linha({ codigo_conta: null, nome_conta: null, descricao: "Nota sem conta" })];
  assert.equal(filtrarLinhas(ls, { q: "sao joao" }).length, 1);
  assert.equal(filtrarLinhas(ls, { q: "DIESEL" })[0].fornecedor, "Posto Mil");
  assert.equal(filtrarLinhas(ls, { conta: "3.04" }).length, 1);
  assert.equal(filtrarLinhas(ls, { conta: "3.0" }).length, 0);
  assert.equal(filtrarLinhas(ls, {}).length, 3);
  assert.equal(filtrarLinhas(ls, { q: "  " }).length, 3);
});

test("totais: receita e despesa nunca somadas; tipo uniforme só quando todos iguais", () => {
  const ls = [linha({ valor: 10.1 }), linha({ valor: 0.2 }), linha({ tipo: "receita", valor: 5 })];
  assert.deepEqual(totais(ls), { receita: 5, despesa: 10.3 });
  assert.equal(tipoUniforme(ls), null);
  assert.equal(tipoUniforme([ls[0], ls[1]]), "despesa");
  assert.equal(tipoUniforme([]), null);
});

test("lote de linha da DRE: uma ação por conta, por mais lançamentos que ela tenha", () => {
  const ls = [linha(), linha(), linha({ codigo_conta: "9.1" })];
  const p = acoesDoControle(ls, { tipo: "linha_dre", valor: "CUSTO_VARIAVEL" });
  assert.deepEqual(p.acoes, [
    { tipo: "linha_dre", alvo: { codigo: "8.20" }, valor: "CUSTO_VARIAVEL" }, { tipo: "linha_dre", alvo: { codigo: "9.1" }, valor: "CUSTO_VARIAVEL" }]);
  assert.deepEqual([p.contas, p.lancamentos, p.puladas], [2, 3, 0]);
  assert.equal(textoDoLote({ tipo: "linha_dre", valor: "x" }, p), "Aplicar a 2 contas (vale para todos os lançamentos delas)");
});

test("lote de linha: conta fora do plano (travada) é pulada e contada", () => {
  const fora = linha({ codigo_conta: "9.9", conta_no_plano: false, acoes: { conta: true, linha_dre: false, natureza: true } });
  const p = acoesDoControle([linha(), fora], { tipo: "linha_dre", valor: "CUSTO_VARIAVEL" });
  assert.equal(p.acoes.length, 1);
  assert.equal(p.puladas, 1);
});

test("lote de conta: uma ação por lançamento/item, com os ids; mês fechado fica de fora", () => {
  const a = linha({ motivo: "sem_codigo_conta", codigo_conta: null, nome_conta: null, conta_no_plano: false, numero_lancamento: "LC-1", conta_id: 5, item_id: null });
  const b = linha({ motivo: "item_sem_conta_automatica", numero_lancamento: "LC-2", item_id: 9, conta_id: 6 });
  const c = linha({ motivo: "sem_codigo_conta", mes_fechado: true, acoes: { conta: false, linha_dre: false, natureza: true }, travas: { conta: "março fechado" } });
  const p = acoesDoControle([a, b, c], { tipo: "conta", valor: "3.01.01" });
  assert.deepEqual(p.acoes, [
    { tipo: "conta", alvo: { numero_lancamento: "LC-1", conta_id: 5 }, valor: "3.01.01" },
    { tipo: "conta", alvo: { numero_lancamento: "LC-2", item_id: 9, conta_id: 6 }, valor: "3.01.01" },
  ]);
  assert.deepEqual([p.lancamentos, p.puladas], [2, 1]);
  assert.equal(textoDoLote({ tipo: "conta", valor: "x" }, p), "Aplicar a 2 lançamentos");
  assert.deepEqual(podeAplicar(c), { ok: false, porque: "março fechado" });
  assert.equal(podeAplicar(a).ok, true);
});

test("lote de natureza: na conta (uma ação por conta) ou só nos lançamentos (mês fechado trava)", () => {
  const ls = [linha({ motivo: "natureza_nao_informada" }), linha({ motivo: "natureza_nao_informada" }),
    linha({ motivo: "natureza_nao_informada", codigo_conta: "8.5", mes_fechado: true })];
  const naConta = acoesDoControle(ls, { tipo: "natureza", valor: "CAPITAL", escopo: "conta" });
  assert.deepEqual(naConta.acoes.map((a) => a.alvo.codigo), ["8.20", "8.5"]);
  assert.equal(textoDoLote({ tipo: "natureza", valor: "x", escopo: "conta" }, naConta), "Aplicar a 2 contas");
  const nosLanc = acoesDoControle(ls, { tipo: "natureza", valor: "CAPITAL", escopo: "lancamento" });
  assert.equal(nosLanc.acoes.length, 2);
  assert.equal(nosLanc.puladas, 1);
  assert.ok(nosLanc.acoes.every((a) => a.alvo.numero_lancamento && !a.alvo.codigo));
  // Conta fora do plano: a natureza só pode ir no lançamento, mesmo no escopo "conta".
  const fora = acoesDoControle([linha({ motivo: "natureza_nao_informada", conta_no_plano: false })], { tipo: "natureza", valor: "CAPITAL", escopo: "conta" });
  assert.equal(fora.acoes[0].alvo.numero_lancamento !== undefined, true);
});

test("sugestões: aceitas só se a ação está liberada; uma conta com vários lançamentos vira uma ação", () => {
  const s = { tipo: "linha_dre" as const, alvo: { codigo: "8.20" }, valor: "CUSTO_VARIAVEL", rotulo: "Linha da DRE: Custo variável (CPV/CMV)", motivo: "x" };
  const ls = [linha({ sugestao: s }), linha({ sugestao: s }), linha({ sugestao: { ...s, alvo: { codigo: "9.1" } }, acoes: { conta: true, linha_dre: false, natureza: true } }), linha()];
  assert.equal(sugestaoAplicavel(ls[0]), true);
  assert.equal(sugestaoAplicavel(ls[2]), false);
  assert.equal(sugestaoAplicavel(ls[3]), false);
  assert.deepEqual(acoesDasSugestoes(ls), [{ tipo: "linha_dre", alvo: { codigo: "8.20" }, valor: "CUSTO_VARIAVEL" }]);
  // Natureza só neste lançamento num mês fechado não é aplicável; na conta do plano é.
  const nat = { tipo: "natureza" as const, alvo: { numero_lancamento: "LC-1" }, valor: "CAPITAL", rotulo: "Natureza: Capital", motivo: "x" };
  assert.equal(sugestaoAplicavel(linha({ sugestao: nat, mes_fechado: true })), false);
  assert.equal(sugestaoAplicavel(linha({ sugestao: { ...nat, alvo: { codigo: "8.5" } }, mes_fechado: true })), true);
});

const fila = (o: Partial<FilaClassificacao["resumo"]> = {}, por: Partial<Record<string, number>> = {}): FilaClassificacao => ({
  periodo: { inicio: "2031-03-01", fim: "2031-03-31" }, regime: "competencia", centro_custo: null, regras_v2: true,
  resumo: { total_pendencias: 6, total_receita: 20000, total_despesa: 9440, mostradas: 6, truncado: false, ...o },
  por_motivo: MOTIVOS.map((m) => ({ motivo: m, rotulo: m, explicacao: "", quantidade: por[m] ?? 0, contas: 0, total_receita: 0, total_despesa: 0, travado: null })),
  por_conta: [], pendencias: [], bloqueios: [], ultimo_lote: null,
});

test("frase: vazia diz que não há nada; cheia conta os lançamentos, separa receita de despesa e aponta o que mais pesa", () => {
  const vazia = fraseClassificar(fila({ total_pendencias: 0, total_receita: 0, total_despesa: 0 }), "março/2031", brl).map((t) => t.t).join("");
  assert.match(vazia, /^Nada a classificar em março\/2031/);
  const f = fraseClassificar(fila({}, { natureza_nao_informada: 2, sem_codigo_conta: 1 }), "março/2031", brl);
  const texto = f.map((t) => t.t).join("");
  assert.match(texto, /Faltam classificar 6 lançamentos em março\/2031 — R\$ 9440,00 de despesa e R\$ 20000,00 de receita \(nunca somadas\)\./);
  assert.match(texto, /O que mais pesa: fora da dre sem motivo \(2\)\./i);
  assert.ok(f.some((t) => t.b && t.t === "6 lançamentos"));
  const um = fraseClassificar(fila({ total_pendencias: 1, total_receita: 0 }, { sem_codigo_conta: 1 }), "hoje", brl).map((t) => t.t).join("");
  assert.match(um, /1 lançamento em hoje — R\$ 9440,00 de despesa\. Enquanto/);
});

test("mensagens do lote e do Desfazer", () => {
  const lote = (o: Partial<ResultadoLote>): ResultadoLote => ({ lote: "classificacao-1", aplicadas: 6, sem_mudanca: 0, alteracoes: 8, avisos: [], acoes: [], ...o });
  assert.equal(mensagemAplicada(lote({ lote: null, aplicadas: 0, alteracoes: 0, sem_mudanca: 2 })), "Nada mudou: tudo já estava classificado assim.");
  assert.equal(mensagemAplicada(lote({})), "6 classificações gravadas (8 campos mudaram). A DRE já usa o novo valor; dá para desfazer.");
  assert.match(mensagemAplicada(lote({ aplicadas: 1, alteracoes: 1, sem_mudanca: 1 })), /^1 classificação gravada \(1 campo mudou\)\..* 1 ação já estava assim\.$/);
  const rev = (o: Partial<ResultadoReversao>): ResultadoReversao => ({ lote: "x", revertidas: 8, ja_revertidas: 0, conflitos: [], nao_encontradas: [], ...o });
  assert.equal(mensagemDesfeita(rev({})), "Desfeito: 8 campos voltaram ao que era.");
  assert.equal(mensagemDesfeita(rev({ revertidas: 0 })), "Esse lote já estava desfeito.");
  assert.match(mensagemDesfeita(rev({ revertidas: 1, conflitos: [{ tabela: "plano_conta_gerencial", id: 1, campo: "linha_dre", valor_atual: "X" }] })),
    /^1 campo voltou ao que era; 1 campo foi mudado à mão depois e ficou como está\.$/);
});

test("drill: o realizado vai para Consultas; o a prazo, para Contas a pagar/receber", () => {
  assert.deepEqual(destinoDaLinha(linha({ pago: true, numero_lancamento: "LC-9" })), { onde: "consultas", documento: "LC-9", relatorio: "a_pagar" });
  assert.deepEqual(destinoDaLinha(linha({ pago: false, tipo: "receita", numero_lancamento: "LC-8" })), { onde: "contas", documento: "LC-8", relatorio: "a_receber" });
});
