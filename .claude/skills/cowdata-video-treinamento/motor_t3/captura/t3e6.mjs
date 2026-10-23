// T3 · Ep. 6 — Produção (Menu › Produção, módulo inteiro): dados fictícios + rotas do stub (EP=t3e6; herda t3e5…t3e1).
// Respostas no formato REAL dos endpoints (backend/fazenda/api/routers/producao.py e reproducao.py), respeitando os parâmetros de filtro do PR #957
// (data_inicio, data_fim, lotes, numeros, rebanho_lactacao, ultimos, tipo, motivos, del_min, del_max, origem):
//   GET /producao/controles          → { controles:[{id, numero, data, producao_kg, del, ordenha1_kg, ordenha2_kg, ordenha3_kg, grupo_primario, lote, lote_fonte}], total }
//   GET /producao/qualidade-leite    → { registros:[{id, numero_matriz|null, data_coleta, ccs, cbt, gordura_pct, proteina_pct, solidos_totais_pct, esd_pct, lactose_pct, nul, tipo, lote, lote_fonte}], total }
//   GET /reproducao/secagens         → { secagens:[{id, numero, data, motivo, escore_condicao_corporal, observacao, lote, lote_fonte}], total }
//   GET /producao/relatorio-bst      → { aplicacoes:[{numero_matriz, data_aplicacao, produto, dose, unidade, responsavel, lote, lote_fonte, categoria, del_aplicacao, del_hoje, origem}], total }
//   GET /producao/pesagens/relatorio → { linhas:[{numero_matriz, grupo_primario, lote, lotes_no_periodo, primeira_data, primeira_peso, ultima_data, ultima_peso, gmd_kg_dia, gpd_kg_dia, num_pesagens}], total }
// Hoje = 23/10/2026 (relógio fixo da captura); período padrão do app = 24/08 a 23/10/2026. O lote é SEMPRE o do dia do registro (lote_fonte "dia"; nunca "(lote atual)").
// Rebanho = o da T1/T2 (dados.mjs, EP=t3e6 herda o estado do fim da T2): 01 - Alta 40 · 02 - Média 40 · 03 - Baixa 29 · 04 - Secas 24 · 06 - Novilhas 46 · 07 - Bezerras 59.
// BST SEMPRE genérico ("Somatotropina bovina (BST)") — nunca nome comercial.
import { animais } from "./dados.mjs";

const HOJE = "2026-10-23", DIAS_DADOS_T2 = 6; // o del_dias do rebanho está ancorado em 17/10/2026
function rng(a) { return () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
const dia = (iso, n) => new Date(Date.parse(iso) + n * 864e5).toISOString().slice(0, 10);
const dif = (a, b) => Math.round((Date.parse(a) - Date.parse(b)) / 864e5);
const cod = (rot) => (rot || "").split(" - ")[0].trim();
const ordem = (a, b) => a.localeCompare(b, "pt-BR", { numeric: true });
const arr1 = (x, d = 1) => Math.round(x * 10 ** d) / 10 ** d;
const lotesOk = (rot, filtro) => !filtro.length || filtro.some((f) => cod(rot) === f || Number(cod(rot)) === Number(f));
const lista = (u, k) => u.searchParams.getAll(k).flatMap((v) => v.split(",")).map((s) => s.trim()).filter(Boolean);
const delHoje = (a) => (a.del_dias ? a.del_dias + DIAS_DADOS_T2 : null);

// ── controles leiteiros: mensais, em 02/09 e 02/10/2026 ──
const DATAS_CTRL = ["2026-09-02", "2026-10-02"];
const BASE_LOTE = { "01": 34, "02": 25.5, "03": 17.5 };
export const CONTROLES = [];
{
  const r = rng(20261023); let id = 1;
  for (const data of DATAS_CTRL.slice().reverse()) {
    for (const a of animais.filter((x) => x.em_lactacao).sort((x, y) => cod(x.grupo_primario).localeCompare(cod(y.grupo_primario)) || ordem(x.numero, y.numero))) {
      const dh = delHoje(a); if (!dh) continue;
      const del = dh - dif(HOJE, data); if (del < 5) continue; // ainda não tinha parido: sem controle
      const pico = 1 - Math.min(0.4, Math.abs(del - 75) / 330);
      const kg = arr1(Math.max(8, BASE_LOTE[cod(a.grupo_primario)] * (0.8 + 0.2 * pico + 0.25 * (r() - 0.5))));
      const o1 = arr1(kg * (0.5 + 0.04 * (r() - 0.5))), o2 = arr1(kg - o1);
      CONTROLES.push({ id: id++, numero: a.numero, raca: "Holandesa", data, ano: 2026, producao_kg: kg, del, ordem_parto: null, data_ult_parto: dia(data, -del),
        ordenha1_kg: o1, ordenha2_kg: o2, ordenha3_kg: null, grupo_primario: a.grupo_primario, lote: a.grupo_primario, lote_fonte: "dia", usuario_nome: "Bernadete" });
    }
  }
}
function controles(u) {
  const di = u.searchParams.get("data_inicio"), df = u.searchParams.get("data_fim"), lotes = lista(u, "lotes"), nums = lista(u, "numeros");
  const reb = u.searchParams.get("rebanho_lactacao") === "true", ult = Number(u.searchParams.get("ultimos")) || 0;
  const vistos = {}; const sai = [];
  for (const c of CONTROLES) { // já em ordem: mais recente primeiro
    if (di && c.data < di) continue; if (df && c.data > df) continue;
    if (nums.length && !nums.includes(c.numero)) continue; if (!lotesOk(c.lote, lotes)) continue;
    if (reb && !animais.find((a) => a.numero === c.numero)?.em_lactacao) continue;
    if (ult) { const n = vistos[c.numero] || 0; if (n >= ult) continue; vistos[c.numero] = n + 1; }
    sai.push(c);
  }
  return { controles: sai, total: sai.length };
}

// ── qualidade do leite: tanque semanal (sextas) e individuais nos dias do controle ──
const QUAL = [];
{
  const r = rng(20261024); let id = 1;
  const u = (lo, hi) => lo + (hi - lo) * r();
  for (let k = 0; k < 9; k++) { // 28/08, 04/09 … 23/10 — de 7 em 7 dias
    const data = dia("2026-08-28", 7 * k);
    QUAL.push({ id: id++, numero_matriz: null, data_coleta: data, ccs: Math.round(u(250, 400)), cbt: Math.round(u(20, 60)), gordura_pct: arr1(u(3.6, 3.9), 2), proteina_pct: arr1(u(3.2, 3.4), 2),
      solidos_totais_pct: arr1(u(12.3, 12.8), 2), esd_pct: arr1(u(8.6, 8.9), 2), lactose_pct: arr1(u(4.5, 4.7), 2), nul: arr1(u(10, 15), 1), tipo: "tanque", lote: null, lote_fonte: null, usuario_nome: "Bernadete" });
  }
  for (const data of ["2026-10-02", "2026-09-02"]) {
    for (const lote of ["01", "02", "03"]) {
      for (const a of animais.filter((x) => x.em_lactacao && cod(x.grupo_primario) === lote).sort((x, y) => ordem(x.numero, y.numero)).slice(0, 8)) {
        QUAL.push({ id: id++, numero_matriz: a.numero, data_coleta: data, ccs: Math.round(u(60, 1100)), cbt: Math.round(u(8, 90)), gordura_pct: arr1(u(3.3, 4.3), 2), proteina_pct: arr1(u(3.0, 3.6), 2),
          solidos_totais_pct: arr1(u(12.0, 13.2), 2), esd_pct: arr1(u(8.4, 9.0), 2), lactose_pct: arr1(u(4.4, 4.8), 2), nul: arr1(u(8, 18), 1), tipo: "individual", lote: a.grupo_primario, lote_fonte: "dia", usuario_nome: "Bernadete" });
      }
    }
  }
}
function qualidade(u) {
  const di = u.searchParams.get("data_inicio"), df = u.searchParams.get("data_fim"), tipo = u.searchParams.get("tipo"), lotes = lista(u, "lotes"), nums = lista(u, "numeros");
  let rs = QUAL.filter((q) => (!di || q.data_coleta >= di) && (!df || q.data_coleta <= df));
  if (tipo === "tanque") rs = rs.filter((q) => !q.numero_matriz); else if (tipo === "individual" || nums.length || lotes.length) rs = rs.filter((q) => q.numero_matriz);
  if (nums.length) rs = rs.filter((q) => nums.includes(q.numero_matriz));
  if (lotes.length) rs = rs.filter((q) => lotesOk(q.lote, lotes));
  return { registros: rs, total: rs.length, tem_faixas_bonificacao: false };
}

// ── secagens: histórico do período (vacas hoje no 04 - Secas); o lote é o de ANTES de secar ──
// [brinco, data, lote ao secar, motivo, ECC]
const SEC_PLANO = [
  ["2305", "2026-10-17", "02 - Média", "rotina", 3.5], ["3338", "2026-10-17", "03 - Baixa", "rotina", 3.25],
  ["5090", "2026-10-09", "03 - Baixa", "rotina", 3.5], ["5011", "2026-10-06", "02 - Média", "rotina", 3.75],
  ["1388", "2026-09-28", "03 - Baixa", "baixa_producao", 3.0], ["5120", "2026-09-22", "02 - Média", "mastite", 3.25],
  ["5144", "2026-09-18", "03 - Baixa", "rotina", 3.5], ["5173", "2026-09-12", "01 - Alta", "doente", 2.75],
  ["5208", "2026-09-05", "03 - Baixa", "casco", 3.0], ["5231", "2026-08-30", "02 - Média", "rotina", 3.5],
];
const SEC = (() => { const secas = animais.filter((a) => a.grupo_primario === "04 - Secas").map((a) => a.numero); // brincos que não existirem nas Secas viram os próximos da lista
  const usados = new Set(SEC_PLANO.filter((s) => secas.includes(s[0])).map((s) => s[0])); const livres = secas.filter((n) => !usados.has(n));
  return SEC_PLANO.map((s, i) => { const n = secas.includes(s[0]) ? s[0] : livres.shift(); return { id: i + 1, numero: n, data: s[1], data_secagem: s[1], motivo: s[3], escore_condicao_corporal: s[4], observacao: null, lote: s[2], lote_fonte: "dia" }; }); })();
function secagens(u) {
  const di = u.searchParams.get("data_inicio"), df = u.searchParams.get("data_fim"), lotes = lista(u, "lotes"), nums = lista(u, "numeros"), mots = lista(u, "motivos");
  const rs = SEC.filter((s) => (!di || s.data >= di) && (!df || s.data <= df) && (!nums.length || nums.includes(s.numero)) && (!mots.length || mots.includes(s.motivo)) && lotesOk(s.lote, lotes))
    .sort((a, b) => (a.data < b.data ? 1 : -1));
  return { secagens: rs, total: rs.length };
}

// ── BST: rotina a cada 14 dias (05/09, 19/09, 03/10, 17/10) + 2 lançamentos avulsos da Sanidade ──
const BST = [];
{
  const r = rng(20261025);
  const pool = animais.filter((a) => a.em_lactacao && delHoje(a) && delHoje(a) - dif(HOJE, "2026-09-05") >= 60).sort(() => r() - 0.5).slice(0, 22)
    .sort((x, y) => cod(x.grupo_primario).localeCompare(cod(y.grupo_primario)) || ordem(x.numero, y.numero));
  const reg = (a, data, origem, resp) => { const dh = delHoje(a); return { numero_matriz: a.numero, data_aplicacao: data, produto: "Somatotropina bovina (BST)", dose: 1, unidade: "seringa", responsavel: resp,
    lote: a.grupo_primario, lote_fonte: "dia", categoria: "Vaca", del_aplicacao: dh - dif(HOJE, data), del_hoje: dh, origem }; };
  for (const data of ["2026-09-05", "2026-09-19", "2026-10-03", "2026-10-17"]) for (const a of pool) { const x = reg(a, data, "Rotina BST", "Adelino"); if (x.del_aplicacao >= 60) BST.push(x); }
  const extra = animais.filter((a) => a.em_lactacao && !pool.includes(a) && delHoje(a) && delHoje(a) - 15 >= 70).slice(0, 2);
  BST.push(reg(extra[0], "2026-10-08", "Sanidade", "Cláudio"), reg(extra[1], "2026-10-20", "Sanidade", "Cláudio"));
  BST.sort((a, b) => (a.data_aplicacao < b.data_aplicacao ? 1 : a.data_aplicacao > b.data_aplicacao ? -1 : ordem(a.numero_matriz, b.numero_matriz)));
}
function bst(u) {
  const di = u.searchParams.get("data_inicio"), df = u.searchParams.get("data_fim"), lotes = lista(u, "lotes"), nums = lista(u, "numeros");
  const dmin = u.searchParams.get("del_min"), dmax = u.searchParams.get("del_max"), orig = (u.searchParams.get("origem") || "").toLowerCase();
  const rs = BST.filter((b) => (!di || b.data_aplicacao >= di) && (!df || b.data_aplicacao <= df) && (!nums.length || nums.includes(b.numero_matriz)) && lotesOk(b.lote, lotes)
    && (dmin == null || dmin === "" || b.del_aplicacao >= Number(dmin)) && (dmax == null || dmax === "" || b.del_aplicacao <= Number(dmax))
    && (!orig || (orig === "rotina" ? b.origem === "Rotina BST" : b.origem === "Sanidade")));
  return { aplicacoes: rs, total: rs.length };
}

// ── pesagens: novilhas e 12 bezerras, duas pesagens no período (16/09 e 16/10) ──
const PES = (() => {
  const r = rng(20261026); const sai = [];
  const novilhas = animais.filter((a) => a.grupo_primario === "06 - Novilhas"), bez = animais.filter((a) => a.grupo_primario === "07 - Bezerras").slice(0, 12);
  for (const a of [...novilhas, ...bez]) {
    const bezerra = a.grupo_primario.startsWith("07"), peso0 = Math.round(bezerra ? 55 + (a.idade_meses || 4) * 17 + 10 * (r() - 0.5) : 105 + (a.idade_meses || 18) * 11 + 30 * (r() - 0.5));
    const gmd = 0.6 + 0.3 * r(), ganho = Math.round(gmd * 30), p1 = "2026-09-16", p2 = "2026-10-16";
    const g = Math.round(ganho / 30 * 1000) / 1000;
    sai.push({ numero_matriz: a.numero, grupo_primario: a.grupo_primario, lote: a.grupo_primario, lotes_no_periodo: [a.grupo_primario], primeira_data: p1, primeira_peso: peso0, ultima_data: p2, ultima_peso: peso0 + ganho, gmd_kg_dia: g, gpd_kg_dia: g, num_pesagens: 2 });
  }
  return sai.sort((x, y) => ordem(x.numero_matriz, y.numero_matriz));
})();
function pesagens(u) {
  const di = u.searchParams.get("data_inicio"), df = u.searchParams.get("data_fim"), lotes = lista(u, "lotes"), nums = lista(u, "numeros");
  const rs = PES.filter((l) => (!di || l.primeira_data >= di) && (!df || l.ultima_data <= df) && (!nums.length || nums.includes(l.numero_matriz)) && lotesOk(l.lote, lotes));
  return { linhas: rs, total: rs.length };
}

export async function t3e6(req, res, p, u, send) {
  if (req.method !== "GET") return false;
  if (p === "/producao/controles") return send(controles(u));
  if (p === "/producao/qualidade-leite") return send(qualidade(u));
  if (p === "/reproducao/secagens") return send(secagens(u));
  if (p === "/producao/relatorio-bst") return send(bst(u));
  if (p === "/producao/pesagens/relatorio") return send(pesagens(u));
  return false;
}
if (process.argv[1]?.endsWith("t3e6.mjs")) {
  const U = (q) => new URL("http://x/?" + q);
  const c = controles(U("data_inicio=2026-08-24&data_fim=2026-10-23&rebanho_lactacao=true&ultimos=1"));
  const porLote = {}; for (const x of c.controles) (porLote[cod(x.lote)] ||= []).push(x.producao_kg);
  console.log("controles Último", c.total, Object.fromEntries(Object.entries(porLote).map(([k, v]) => [k, [v.length, arr1(v.reduce((s, y) => s + y, 0) / v.length)]])));
  console.log("controles 01+02", controles(U("lotes=01&lotes=02&ultimos=1")).total, "todos", controles(U("rebanho_lactacao=true")).total);
  console.log(JSON.stringify(c.controles.slice(0, 3)));
  console.log("tanque", qualidade(U("tipo=tanque")).total, JSON.stringify(qualidade(U("tipo=tanque")).registros[0]), "indiv", qualidade(U("tipo=individual")).total);
  console.log("secagens", secagens(U("")).total, JSON.stringify(SEC.map((s) => [s.numero, s.data, s.lote, s.motivo])));
  console.log("bst", bst(U("")).total, "rotina", bst(U("origem=rotina")).total, "sanidade", bst(U("origem=sanidade")).total, "del60-120", bst(U("del_min=60&del_max=120")).total, JSON.stringify(BST[0]));
  console.log("pesagens", PES.length, JSON.stringify(PES.slice(0, 2)));
}
