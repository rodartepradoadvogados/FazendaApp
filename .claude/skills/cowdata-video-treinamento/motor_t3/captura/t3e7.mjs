// T3 · Ep. 7 — Alimentação: Lançar nova dieta e Necessidade Mensal (Menu › Alimentação; fecha o módulo): dados fictícios + rotas do stub (EP=t3e7; herda t3e6…t3e1).
// Coerente com o Ep. 5 (mesmo rebanho e mesmas dietas: t3e5.mjs): o episódio LANÇA uma dieta nova para o lote 02 - Média (41 animais; a ativa do Ep. 5 tem 2 tratos 50/50) e o
// stub aplica o POST como o backend real (rules/dieta_lancamento.py): com encerrar_anterior a dieta ativa do lote é encerrada NA DATA DE INÍCIO da nova (data_efetivo_encerramento = data_abertura).
// Rotas (formatos de backend/fazenda/api/routers/alimentacao.py):
//   GET  /estoque/                              → itens de estoque (alimentos genéricos, sem marca) para o seletor "Selecionar silagem/alimento…"
//   GET  /alimentacao/dietas/contexto/{lote}    → herdado do t3e5, com DEL médio / média CL / último CL do lote 02 - Média
//   POST /alimentacao/dietas                    → cria a dieta (tratos_pct, sobra_posicao_leitura, itens) e encerra a anterior se pedido
//   GET  /alimentacao/necessidade-mensal        → { itens:[{ingrediente, unidade, consumo_dia, necessidade_mes, ensacado, kg_por_saco, sacos_mes, ...}] } = soma das dietas ATIVAS × 30
// Hoje = 24/10/2026 (relógio fixo da captura).
import { DIETAS, planoAlimentacao, contexto as contexto5, t3e5 } from "./t3e5.mjs";
const DIETAS0 = structuredClone(DIETAS);
const N = { 1: 40, 2: 41, 5: 12 }; // efetivo dos lotes (iguais ao Ep. 5)
export const POSTS7 = [];
// itens de estoque de alimentação: embalagem em "saca Xkg" no campo unidade_embalagem/medida (rules/alimentacao.resolver_kg_por_unidade); silagem a granel
const EST = [
  { id: 101, nome: "Silagem de milho", categoria: "Volumoso", quantidade: 96000, unidade: "kg", embalagem: null },
  { id: 102, nome: "Concentrado lactação", categoria: "Concentrado", quantidade: 18400, unidade: "kg", embalagem: 40 },
  { id: 103, nome: "Feno de tifton", categoria: "Volumoso", quantidade: 5200, unidade: "kg", embalagem: null },
  { id: 104, nome: "Núcleo mineral", categoria: "Mineral", quantidade: 640, unidade: "kg", embalagem: 25 },
  { id: 105, nome: "Caroço de algodão", categoria: "Concentrado", quantidade: 3200, unidade: "kg", embalagem: null },
];
const estoque = () => ({ itens: EST.map((e) => ({ id: e.id, nome: e.nome, categoria: e.categoria, quantidade: e.quantidade, unidade: e.unidade, estocavel: true, ativo: true, finalidade: "Ração/Alimento", alimento_id: e.id, estoque_semen_id: null,
  unidade_embalagem: e.embalagem ? "saca" : null, medida_embalagem: e.embalagem ? "kg/saca" : null, quantidade_embalagem: e.embalagem })) });
const r2 = (x) => Math.round(x * 100) / 100;
export function necessidade() {
  const tot = new Map();
  for (const d of DIETAS.filter((x) => !x.data_efetivo_encerramento)) for (const [nome, cab] of d.itens) tot.set(nome, r2((tot.get(nome) || 0) + cab * N[d.lote]));
  return { itens: [...tot.entries()].map(([ingrediente, consumo_dia]) => { const e = EST.find((x) => x.nome === ingrediente), kg_por_saco = e?.embalagem ?? null, necessidade_mes = r2(consumo_dia * 30);
    return { ingrediente, unidade: "kg", consumo_dia, necessidade_mes, ensacado: kg_por_saco != null, kg_por_saco, sacos_mes: kg_por_saco ? Math.ceil(necessidade_mes / kg_por_saco) : null, item_estoque_vinculado: true, alimento_sem_vinculo: false }; }) };
}
function contexto(lote) {
  const c = contexto5(lote); if (!c) return c;
  if (lote === 2) Object.assign(c, { del_medio: 164, media_cl: 26.3, data_ult_cl: "2026-10-02" });
  return c;
}
export async function t3e7(req, res, p, u, send, corpo) {
  if (p === "/__reset") { DIETAS.splice(0, DIETAS.length, ...structuredClone(DIETAS0)); POSTS7.length = 0; return false; }
  if (req.method === "GET" && p === "/estoque/") return send(estoque());
  if (req.method === "GET" && p === "/alimentacao/necessidade-mensal") return send(necessidade());
  let m;
  if (req.method === "GET" && (m = p.match(/^\/alimentacao\/dietas\/contexto\/(\d+)$/))) { const c = contexto(Number(m[1])); return c ? send(c) : send({ detail: "sem dieta" }, 404); }
  if (req.method === "POST" && p === "/alimentacao/dietas") {
    const b = await corpo(req); POSTS7.push(b);
    const ativa = DIETAS.find((d) => d.lote === b.lote && !d.data_efetivo_encerramento);
    if (ativa && !b.encerrar_anterior) return send({ detail: `O lote ${b.lote} já tem uma dieta ativa.` }, 409);
    if (ativa) ativa.data_efetivo_encerramento = b.data_abertura;
    const n = N[b.lote] || 1, id = Math.max(...DIETAS.map((d) => d.id)) + 1;
    DIETAS.push({ id, lote: b.lote, data_abertura: b.data_abertura, data_prevista_encerramento: b.data_prevista_encerramento ?? null, data_efetivo_encerramento: null,
      tratos: b.tratos_pct, posicao: b.sobra_posicao_leitura, itens: b.itens.map((i) => [i.alimento, Math.round((i.quantidade / n) * 1000) / 1000]) });
    return send({ id, lote: b.lote, ativa: true });
  }
  return t3e5(req, res, p, u, send);
}
if (process.argv[1]?.endsWith("t3e7.mjs")) console.log(JSON.stringify({ necessidadeAntes: necessidade(), ctx2: contexto(2) }, null, 1));
