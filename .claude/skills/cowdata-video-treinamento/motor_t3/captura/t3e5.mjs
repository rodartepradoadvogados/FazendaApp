// T3 · Ep. 5 — Alimentação: Plano por lote e Consultar dietas (Menu › Alimentação): dados fictícios + rotas do stub (EP=t3e5; herda t3e4/t3e3/t3e2/t3e1).
// Formatos idênticos aos de backend/fazenda/api/routers/alimentacao.py:
//   GET /alimentacao/                      → { por_lote:[{lote, categoria, efetivo, itens:[{ingrediente, por_cabeca, unidade, efetivo, consumo_dia}], tratos_pct}], consumo_total }
//   GET /alimentacao/dietas                → [{id, lote, data_abertura, data_prevista_encerramento, data_efetivo_encerramento, ativa, ...resumo de tratos}]
//   GET /alimentacao/dietas/{id}/apresentacao → { lote, nome, qtd_animais, tratos_pct, num_tratos, tratos:[{trato,pct,vagao_kg}], itens:[{..., por_trato}], vagao_kg_dia }
//   GET /alimentacao/dietas/contexto/{lote} → contexto do "Lançar nova dieta" (nº de animais, última dieta com tratos)
// Alimentos genéricos (sem marca), coerentes com a T2 Ep. 11 (01 - Alta, 40 vacas: silagem 35 kg/cab). Tratos SEMPRE os cadastrados na dieta:
//   dieta ativa do 01 - Alta = 3 tratos 40/30/30; a encerrada anterior = 2 tratos 50/50; 02 - Média = 2 × 50/50 cadastrados; 05 - Pré-parto = SEM cadastro (2 × 50% por padrão).
// Hoje = 17/10/2026 (relógio fixo da captura).
const LOTES = { 1: { nome: "Alta", n: 40 }, 2: { nome: "Média", n: 41 }, 5: { nome: "Pré-parto", n: 12 } };
// [alimento, kg por cabeça]
const ITENS = {
  1: [["Silagem de milho", 35], ["Concentrado lactação", 9], ["Feno de tifton", 2], ["Núcleo mineral", 0.25]],
  2: [["Silagem de milho", 30], ["Concentrado lactação", 6.5], ["Feno de tifton", 2.5], ["Núcleo mineral", 0.2]],
  5: [["Silagem de milho", 25], ["Concentrado lactação", 4], ["Feno de tifton", 3]],
};
const ITENS_ENCERRADA_1 = [["Silagem de milho", 33], ["Concentrado lactação", 8.5], ["Feno de tifton", 2], ["Núcleo mineral", 0.25]];
const ITENS_ENCERRADA_2 = [["Silagem de milho", 28], ["Concentrado lactação", 6], ["Feno de tifton", 2.5], ["Núcleo mineral", 0.2]];
const r2 = (x) => Math.round(x * 100) / 100;
// dietas: id, lote, abertura, prevista, encerramento efetivo, tratos (null = sem cadastro), posição da leitura da sobra, itens
export const DIETAS = [
  { id: 1, lote: 1, data_abertura: "2026-10-01", data_prevista_encerramento: "2026-12-31", data_efetivo_encerramento: null, tratos: [40, 30, 30], posicao: 3, itens: ITENS[1] },
  { id: 2, lote: 1, data_abertura: "2026-08-01", data_prevista_encerramento: "2026-09-30", data_efetivo_encerramento: "2026-09-30", tratos: [50, 50], posicao: 2, itens: ITENS_ENCERRADA_1 },
  { id: 3, lote: 2, data_abertura: "2026-09-15", data_prevista_encerramento: "2026-12-15", data_efetivo_encerramento: null, tratos: [50, 50], posicao: 2, itens: ITENS[2] },
  { id: 4, lote: 5, data_abertura: "2026-09-20", data_prevista_encerramento: "2026-11-30", data_efetivo_encerramento: null, tratos: null, posicao: null, itens: ITENS[5] },
  { id: 5, lote: 2, data_abertura: "2026-06-01", data_prevista_encerramento: "2026-09-14", data_efetivo_encerramento: "2026-09-14", tratos: [50, 50], posicao: 2, itens: ITENS_ENCERRADA_2 },
];
const pcts = (d) => d.tratos ?? [50, 50];
const resumo = (d) => ({ num_tratos: pcts(d).length, tratos_pct: pcts(d), tratos_configurados: !!d.tratos, sobra_posicao_leitura: d.tratos ? d.posicao : null });
const dividir = (total, p) => p.map((x) => Math.round(total * x) / 100); // igual a dividirPorTrato (lib/tratos.ts)
export const planoAlimentacao = () => ({
  por_lote: [1, 2, 5].map((l) => { const d = DIETAS.find((x) => x.lote === l && !x.data_efetivo_encerramento), n = LOTES[l].n;
    return { lote: l, categoria: LOTES[l].nome, efetivo: n, tratos_pct: pcts(d),
      itens: d.itens.map(([ingrediente, cab]) => ({ ingrediente, por_cabeca: cab, unidade: "kg", efetivo: n, consumo_dia: r2(cab * n) })) }; }),
  consumo_total: [],
});
export const listaDietas = () => DIETAS.map((d) => ({ id: d.id, lote: d.lote, responsavel: null, observacao: null, base_quantidade: "total", data_abertura: d.data_abertura,
  data_prevista_encerramento: d.data_prevista_encerramento, data_efetivo_encerramento: d.data_efetivo_encerramento, ativa: !d.data_efetivo_encerramento,
  usuario_id: 1, usuario_nome: "Bernadete", tratos_pct: d.tratos ?? undefined, ...resumo(d), itens_programados: [] }))
  .sort((a, b) => (a.data_abertura < b.data_abertura ? 1 : -1));
export function apresentacao(id) {
  const d = DIETAS.find((x) => x.id === id); if (!d) return null;
  const n = LOTES[d.lote].n, p = pcts(d), unico = p.every((x) => x === p[0]);
  const itens = d.itens.map(([alimento, cab]) => { const tot = r2(cab * n), pt = dividir(tot, p); return { alimento, unidade: "kg", total_dia: tot, por_cabeca: cab, total_trato: unico ? pt[0] : null, por_trato: pt }; });
  const vagao = r2(itens.reduce((s, i) => s + i.total_dia, 0)), vt = dividir(vagao, p);
  return { lote: d.lote, nome: LOTES[d.lote].nome, qtd_animais: n, data_abertura: d.data_abertura, data_prevista_encerramento: d.data_prevista_encerramento, ...resumo(d), itens,
    vagao_kg_dia: vagao, vagao_kg_trato: unico ? vt[0] : null, tratos: p.map((x, i) => ({ trato: i + 1, pct: x, vagao_kg: vt[i] })) };
}
export function contexto(lote) {
  const d = DIETAS.find((x) => x.lote === lote && !x.data_efetivo_encerramento); if (!d) return null;
  const n = LOTES[lote].n;
  return { lote, nome: LOTES[lote].nome, qtd_animais: n, del_medio: 118, media_cl: 31.4, data_ult_cl: "2026-10-16", animais: [],
    ultima_dieta: { data_abertura: d.data_abertura, data_prevista_encerramento: d.data_prevista_encerramento, responsavel: null, base_quantidade: "total", leite_bezerros_kg_dia: null, leite_por_bezerro_kg_dia: null,
      itens: d.itens.map(([alimento, cab]) => ({ alimento, unidade: "kg", total_dia: r2(cab * n), por_cabeca: cab })), ...resumo(d) } };
}
export async function t3e5(req, res, p, u, send) {
  if (req.method !== "GET") return false;
  if (p === "/alimentacao/") return send(planoAlimentacao());
  if (p === "/alimentacao/dietas") return send(listaDietas());
  let m;
  if ((m = p.match(/^\/alimentacao\/dietas\/(\d+)\/apresentacao$/))) { const a = apresentacao(Number(m[1])); return a ? send(a) : send({ detail: "Dieta não encontrada" }, 404); }
  if ((m = p.match(/^\/alimentacao\/dietas\/contexto\/(\d+)$/))) { const c = contexto(Number(m[1])); return c ? send(c) : send({ detail: "sem dieta" }, 404); }
  return false;
}
if (process.argv[1]?.endsWith("t3e5.mjs")) console.log(JSON.stringify({ plano: planoAlimentacao(), dietas: listaDietas().map((d) => [d.id, d.lote, d.ativa]), ap1: apresentacao(1), ap2: apresentacao(2) }, null, 1));
