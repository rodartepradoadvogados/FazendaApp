// T3 · Ep. 1 — Agenda Reprodutiva: dados fictícios + rotas do stub (cards salvos COM ESTADO, resultados calculados pela
// configuração do card, listas fixas, ficha). Usado por stub-api.mjs quando EP=t3e1. Data de referência 17/10/2026.
import { animais } from "./dados.mjs";

const dia = (n) => new Date(Date.parse("2026-10-17") + n * 864e5).toISOString().slice(0, 10);
const A = "01 - Alta", M = "02 - Média", B = "03 - Baixa";
const base = (numero, lote, o) => ({ numero_matriz: numero, categoria: "Vaca", lote_atual: lote, estado: null, del_dias: null, dias_gestacao: null, dias_desde_servico: null, data_servico: null, parto_previsto: null, diagnostico: null, data_diagnostico: null, diagnostico_reconfirmacao: null, data_reconfirmacao: null, retoque: false, fase: null, ainda_nao: false, dias_para_prazo: null, prazo_tipo: null, ...o });
const DIAS_TOQUE = 30, DIAS_RECONF = 60;

// ── rebanho reprodutivo fictício (cada item já traz fase/ainda_nao como o backend calcularia) ──
const ins = (n, l, dias, del, o = {}) => base(n, l, { estado: "inseminada", del_dias: del, dias_desde_servico: dias, data_servico: dia(-dias), fase: "a_tocar", prazo_tipo: "toque", ...o });
const INSEMINADAS = [
  ins("4318", A, 33, 118),
  ins("4731", A, 38, 139, { diagnostico: "INDEFINIDO", data_diagnostico: dia(-3) }),
  ins("4521", A, 47, 142),
  ins("4896", A, 55, 151, { diagnostico: "INDEFINIDO", data_diagnostico: dia(-6) }),
  ins("4602", M, 22, 96, { ainda_nao: true, dias_para_prazo: 8 }),
  ins("4655", M, 41, 124), ins("4690", M, 57, 133),
  ins("1388", B, 12, 201, { ainda_nao: true, dias_para_prazo: 18 }),
];
const gest = (n, l, dg, dxToque, dToque, rec, dRec, retoque) => base(n, l, {
  estado: "gestante", dias_gestacao: dg, dias_desde_servico: dg, data_servico: dia(-dg), parto_previsto: dia(280 - dg),
  diagnostico: dxToque, data_diagnostico: dToque, diagnostico_reconfirmacao: rec, data_reconfirmacao: dRec, retoque,
  ...(rec === "POSITIVO" ? { fase: "reconfirmada" } : (() => { const falta = DIAS_TOQUE + DIAS_RECONF - dg; return { fase: "a_reconfirmar", ainda_nao: falta > 0, dias_para_prazo: falta > 0 ? falta : null, prazo_tipo: "reconfirmacao" }; })()),
});
const GESTANTES = [
  gest("2480", B, 66, "POSITIVO", dia(-33), "POSITIVO", dia(-2), true),
  gest("3127", M, 71, "NEGATIVO", dia(-39), "POSITIVO", dia(-9), true),
  gest("3302", M, 88, "POSITIVO", dia(-56), null, null, true),
  gest("3871", M, 84, "POSITIVO", dia(-52), null, null, true),
  gest("2956", B, 79, "POSITIVO", dia(-47), null, null, true),
  // fora do período 60–89 (não entram no card, mas contam nas listas): gestantes antigas
  gest("1190", A, 142, "POSITIVO", dia(-110), "POSITIVO", dia(-80), false),
  gest("1204", A, 214, "POSITIVO", dia(-182), "POSITIVO", dia(-152), false),
];
const VAZIAS_ATRASADAS = [["1045", M, 187], ["3990", M, 201], ["2388", M, 214], ["4033", M, 236], ["4078", M, 254], ["1450", B, 262]].map(([n, l, d]) => base(n, l, { estado: "vazia_atrasada", del_dias: d }));
const PEV = [["3601", A, 52], ["3644", A, 58], ["3689", A, 61], ["3702", A, 66], ["3733", A, 71], ["3758", A, 79], ["3790", A, 86]].map(([n, l, d]) => base(n, l, { estado: "pev", del_dias: d }));
const MASTER = [...INSEMINADAS, ...GESTANTES, ...VAZIAS_ATRASADAS, ...PEV];

const SIT = { pev: (i) => i.estado === "pev", inseminada: (i) => i.estado === "inseminada", gestante: (i) => i.estado === "gestante", vazia: (i) => ["vazia", "vazia_atrasada"].includes(i.estado), vazia_atrasada: (i) => i.estado === "vazia_atrasada", a_descartar: () => false };
const EIXO = { pev: "del_dias", inseminada: "dias_desde_servico", gestante: "dias_gestacao" };
function resultado(config) {
  let r = MASTER.filter(SIT[config.situacao] || (() => false));
  if (config.lotes?.length) r = r.filter((i) => config.lotes.includes(i.lote_atual));
  if (config.categoria === "novilha") r = [];
  const eixo = EIXO[config.situacao];
  if (eixo && config.periodos?.length) r = r.filter((i) => config.periodos.some(([a, b]) => i[eixo] != null && i[eixo] >= a && i[eixo] <= b));
  return r;
}
const CARDS0 = [
  { id: "t3-vaz", nome: "Vazias atrasadas", config: { categoria: "todas", lotes: [], situacao: "vazia_atrasada", periodos: [], somente_atrasadas: false, exceto_atrasadas: false } },
  { id: "t3-gest", nome: "Gestantes 60–89 dias", config: { categoria: "todas", lotes: [], situacao: "gestante", periodos: [[60, 89]], somente_atrasadas: false, exceto_atrasadas: false } },
  { id: "t3-pev", nome: "PEV 45–90 dias", config: { categoria: "todas", lotes: [A], situacao: "pev", periodos: [[45, 90]], somente_atrasadas: false, exceto_atrasadas: false } },
];
let cards = structuredClone(CARDS0);

// ── listas fixas (Agenda do veterinário) ──
const seq = (ini, n, o) => Array.from({ length: n }, (_, k) => ({ numero_matriz: String(ini + k * 7), categoria: "Vaca", ...o(k) }));
const ia = (i) => ({ numero_matriz: i.numero_matriz, categoria: "Vaca", dias_inseminada: i.dias_desde_servico, data_servico: i.data_servico });
const LISTAS = {
  inseminadas_1_29: INSEMINADAS.filter((i) => i.dias_desde_servico < 30).map(ia).concat(seq(2210, 5, (k) => ({ dias_inseminada: 5 + k * 5, data_servico: dia(-(5 + k * 5)) }))),
  inseminadas_30_59: INSEMINADAS.filter((i) => i.dias_desde_servico >= 30 && i.dias_desde_servico <= 59).map(ia).concat(seq(2790, 5, (k) => ({ dias_inseminada: 31 + k * 5, data_servico: dia(-(31 + k * 5)) }))),
  inseminadas_60_mais: seq(1810, 4, (k) => ({ dias_inseminada: 63 + k * 9, data_servico: dia(-(63 + k * 9)) })),
  novilhas_aptas_vazias: seq(6010, 14, () => ({ categoria: "Novilha", peso: 380 })),
  novilhas_gestantes: seq(6310, 9, () => ({ categoria: "Novilha", dias_para_parto: 120 })),
  verificar_pre_parto: seq(5110, 5, (k) => ({ dias_para_parto: 20 - k * 3 })),
  vacas_gestantes: seq(1010, 66, (k) => ({ dias_para_parto: 30 + k * 3 })),
  vazias_por_diagnostico: seq(3910, 9, () => ({ motivo: "Diagnóstico negativo" })),
  pendentes_classificacao: seq(7010, 4, () => ({})),
};
const TOTAIS = Object.fromEntries(Object.entries(LISTAS).map(([k, v]) => [k, v.length]));

const FICHAS = { "4318": "Jabuticaba", "4731": "Margarida", "4521": "Estrela", "4896": "Pérola", "3302": "Violeta", "3871": "Cereja" };

export async function t3e1(req, res, p, u, send, corpo) {
  if (p === "/__reset") { cards = structuredClone(CARDS0); return send({ ok: true }); }
  if (p === "/reproducao/agenda-reprodutiva/cards-config") {
    if (req.method === "PUT") { const b = await corpo(req); cards = b.cards || []; return send({ ok: true }); }
    return send({ cards, atualizado_em: "2026-10-17T09:00:00" });
  }
  if (p === "/reproducao/agenda-reprodutiva/cards" && req.method === "POST") {
    const b = await corpo(req); const resultados = {};
    for (const c of b.cards || []) { const it = resultado(c.config); resultados[c.id] = { total: it.length, itens: it }; }
    return send({ data_referencia: "2026-10-17", parametros: { dias_toque: DIAS_TOQUE, dias_reconfirmacao: DIAS_RECONF }, resultados });
  }
  if (p === "/reproducao/agenda-reprodutiva/card" && req.method === "POST") { const b = await corpo(req); const it = resultado(b); return send({ data_referencia: "2026-10-17", total: it.length, itens: it }); }
  if (p === "/reproducao/agenda-veterinario") return send({ data_referencia: "2026-10-17", listas: LISTAS, totais: TOTAIS });
  const m = p.match(/^\/animais\/([^/]+)\/ficha$/);
  if (m) {
    const it = MASTER.find((i) => i.numero_matriz === m[1]);
    return send({ animal: { numero: m[1], nome: FICHAS[m[1]] || null, raca: "Holandesa", categoria_completa: "Vaca lactação", categoria_abrev: "Vaca", ativo: true, grupo_primario: it?.lote_atual || A, sexo: "F" } });
  }
  return false;
}
