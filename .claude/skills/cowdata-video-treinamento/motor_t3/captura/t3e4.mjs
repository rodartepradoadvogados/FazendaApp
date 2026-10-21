// T3 · Ep. 4 — Ciclos de 21 dias (Menu › Reprodução): dados fictícios + rota do stub (EP=t3e4; herda t3e3/t3e2/t3e1).
// Formato idêntico ao de GET /reproducao/ciclos-21-dias (backend/fazenda/api/routers/reproducao.py + rules/programa_reprodutivo.py):
//   { ancora, modo, categoria, periodo, ciclos:[{ciclo, inicio, fim, br_elig, bred, taxa_servico, pg_elig, preg, taxa_prenhez, taxa_concepcao,
//     servicos_com_resultado, janela_dg_completa, animais:{br_elig,bred,pg_elig,preg}}], resumo (média PONDERADA pelo denominador), metas, parametros, ressalva_historica }
// Data de referência 17/10/2026 (relógio fixo), âncora = hoje, modo "fim", 6 ciclos de 21 dias (14/06 a 17/10). dias_resultado_conhecido = 28:
// um ciclo só tem a janela de diagnóstico completa se fim + 28 dias <= hoje — por isso os ciclos 5 e 6 saem "em apuração" (regra real do backend).
// Números coerentes: bred <= br_elig, pg_elig <= br_elig, preg <= bred e <= pg_elig; taxas = razões; nos ciclos fechados servicos_com_resultado = bred
// (toda IA com 28+ dias entra na conta). No ciclo 5 só contam as IAs com 28+ dias (ou resultado conhecido); no 6 nenhuma IA tem 28 dias (preg = 0).
// Brincos: os do rebanho fictício (lotes 01–03 e novilhas do 06), com as vacas conhecidas da T1/T2 nos baldes certos (ver "FIXAS").
import { animais, estadosEp2 } from "./dados.mjs";

const HOJE = "2026-10-17", DIAS = 21, N = 6, DIAS_RES = 28;
const dia = (iso, n) => new Date(Date.parse(iso) + n * 864e5).toISOString().slice(0, 10);
const INICIO1 = dia(HOJE, -(N * DIAS - 1));
function rng(a) { return () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
const r = rng(Number(process.env.SEED_CICLOS || 12));
const embaralha = (v) => { const a = [...v]; for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(r() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; };
const ordem = (a, b) => a.localeCompare(b, "pt-BR", { numeric: true });
const inicioDe = (k) => dia(INICIO1, k * DIAS), fimDe = (k) => dia(INICIO1, (k + 1) * DIAS - 1);
const janela = (k) => dia(fimDe(k), DIAS_RES) <= HOJE;

// ── montagem dos baldes, ciclo a ciclo ──
// Os números de cada ciclo (BR ELIG, BRED, PG ELIG, PREG, serviços com resultado) vêm da tabela PLANO; QUEM entra em cada balde sai do rebanho fictício:
//  · gestantes recentes (dias de gestação ≤ 125 em estadosEp2): BRED e PREG no ciclo da IA (data = hoje − dias de gestação), elegíveis do fim do PEV até ali;
//  · inseminadas (31 vacas, IA há 0 a 40 dias): BRED no ciclo da IA; sem DG continuam "aptas" (regra R4) e voltam no BR ELIG do ciclo seguinte;
//  · vazias (aptas e atrasadas): elegíveis desde o fim do PEV (DEL − 50 dias), às vezes servidas sem pegar;
//  · novilhas do 06 - Novilhas: elegíveis desde que passaram da idade apta; as que concebem aparecem como PREG e saem da fila;
//  · parto recente (DEL < 50), gestante há mais de 125 dias e baixadas ficam fora (estavam secas/gestantes durante os 6 ciclos).
// PLANO = [br_elig, bred, pg_elig, preg, servicos_com_resultado]. Fechados (1–4): servicos_com_resultado = bred (toda IA com 28+ dias entra, mesmo sem DG).
// Ciclo 5: só as IAs com 28+ dias contam (e a prenhez ainda é parcial); ciclo 6: nenhuma IA tem 28 dias (preg = 0, concepção sem denominador).
const PLANO = [
  [46, 30, 44, 11, 30],
  [48, 31, 46, 11, 31],
  [47, 29, 45, 10, 29],
  [44, 26, 42, 10, 26],   // ciclo 4 = o ciclo-exemplo do episódio: 26 ÷ 44 = 59,1% · 10 ÷ 42 = 23,8% · 10 ÷ 26 = 38,5%
  [46, 29, 44, 8, 24],
  [41, 23, 39, 0, 0],
];
const lote = (a) => (a.grupo_primario || "").slice(0, 2);
const ciclo_de = (iso) => Math.floor((Date.parse(iso) - Date.parse(INICIO1)) / 864e5 / DIAS);
const PEV = 50, IDADE_APTA_MESES = 15, ate28 = dia(HOJE, -DIAS_RES);
const vacas = animais.filter((a) => ["01", "02", "03"].includes(lote(a)) && estadosEp2[a.numero]);
const novilhas = animais.filter((a) => lote(a) === "06");
const cows = [];   // {n, tipo, ini, kc, dataIA}
for (const a of vacas) {
  const e = estadosEp2[a.numero]; if (["nao_apta", "pev"].includes(e.estado)) continue;
  if (e.estado === "gestante" && (e.gest ?? 999) > 125) continue;
  const ini = Math.max(0, ciclo_de(dia(HOJE, -(a.del_dias ?? 0) + PEV)));
  if (e.estado === "gestante") { const d = dia(HOJE, -e.gest); cows.push({ n: a.numero, tipo: "A", ini: Math.min(ini, ciclo_de(d)), kc: ciclo_de(d), dataIA: d }); }
  else if (e.estado === "inseminada") { const d = dia(HOJE, -(e.ia ?? 0)); cows.push({ n: a.numero, tipo: "B", ini: Math.min(ini, ciclo_de(d)), kc: ciclo_de(d), dataIA: d }); }
  else cows.push({ n: a.numero, tipo: "C", ini, kc: null, dataIA: null });
}
const nov = novilhas.map((a) => ({ n: a.numero, ini: Math.max(0, ciclo_de(dia(HOJE, Math.round((IDADE_APTA_MESES - (a.idade_meses ?? 18)) * 30.4)))) })).sort((x, y) => ordem(x.n, y.n));
// vacas que a T2/T3 mostram vazias hoje (aptas no Ep. 2, em protocolo de IATF nos Eps. 2–3): não foram inseminadas no ciclo 6
const NAO_SERVIDAS_C6 = new Set(["4033", "4078", "3990", "3054", "3065", "3118", "3169", "3265", "3344", "4210"]);
const gravidasNov = new Set();   // novilhas que já concebeu: saem da fila
const dataIAnov = {};
export const ciclos = [];
for (let k = 0; k < N; k++) {
  const [nBr, nBred, nPg, nPreg, nSc] = PLANO[k];
  // vacas na janela do ciclo (A até a concepção; B até hoje — inseminada sem DG segue apta; C até hoje)
  const fixos = cows.filter((c) => c.ini <= k && (c.tipo === "A" ? k <= c.kc : true)).map((c) => c.n);
  const br = new Set(fixos);
  const aPreg = cows.filter((c) => c.tipo === "A" && c.kc === k && k <= 4).length;
  const novDisp0 = nov.filter((x) => x.ini <= k && !gravidasNov.has(x.n)).map((x) => x.n);
  const pregNov = embaralha(novDisp0.length >= nPreg - aPreg ? novDisp0 : nov.filter((x) => !gravidasNov.has(x.n)).map((x) => x.n)).slice(0, Math.max(0, nPreg - aPreg));
  for (const n of pregNov) br.add(n);
  const novDisp = novDisp0.filter((n) => !pregNov.includes(n));
  const outras = embaralha(novDisp.length + br.size >= nBr ? novDisp : [...novDisp, ...nov.filter((x) => x.ini > k && !gravidasNov.has(x.n)).map((x) => x.n)]);
  // se as vacas já passam do alvo, tira vazias (tipo C) ao acaso — são as únicas sem data amarrada ao ciclo
  const C = embaralha(fixos.filter((n) => cows.find((c) => c.n === n).tipo === "C"));
  while (br.size > nBr && C.length) br.delete(C.pop());
  for (const n of outras) { if (br.size >= nBr) break; br.add(n); }
  const ehNov = (n) => nov.some((x) => x.n === n), tipoDe = (n) => cows.find((c) => c.n === n)?.tipo ?? "N";
  const sorteiaDia = (max = DIAS) => dia(inicioDe(k), Math.floor(r() * max));
  // PREG: gestantes recentes que concebem neste ciclo + novilhas elegíveis até completar (no ciclo 5, IA nos primeiros 12 dias, para já haver DG)
  const preg = new Set(cows.filter((c) => c.tipo === "A" && c.kc === k && br.has(c.n) && k <= 4).map((c) => c.n));
  const bred = new Set(), dataIA = {};
  for (const c of cows) if (c.kc === k && br.has(c.n)) { bred.add(c.n); dataIA[c.n] = c.dataIA; }
  for (const n of [...pregNov, ...embaralha([...br].filter((n) => ehNov(n) && !pregNov.includes(n)))]) { if (preg.size >= nPreg) break; preg.add(n); bred.add(n); dataIA[n] = sorteiaDia(k === 4 ? 12 : DIAS); gravidasNov.add(n); }
  // BRED: completa com vazias/novilhas servidas que não pegaram (inseminada sem DG de ciclo anterior e gestante depois da concepção não são servidas de novo)
  const pegaveis = embaralha([...br].filter((n) => !bred.has(n) && !(k === N - 1 && NAO_SERVIDAS_C6.has(n)) && !(tipoDe(n) === "B" && k >= cows.find((c) => c.n === n).kc) && !(tipoDe(n) === "A" && k >= cows.find((c) => c.n === n).kc)));
  let jaConta = [...bred].filter((n) => dataIA[n] <= ate28).length;
  for (const n of pegaveis) { if (bred.size >= nBred) break; bred.add(n);
    if (k === 4) { dataIA[n] = jaConta < nSc ? sorteiaDia(13) : dia(INICIO1, 4 * DIAS + 14 + Math.floor(r() * 7)); if (dataIA[n] <= ate28) jaConta++; }   // ciclo 5: só as IAs de até 19/09 já têm 28 dias
    else dataIA[n] = sorteiaDia(); }
  // PG ELIG = BR ELIG menos baixadas (nunca quem foi servida)
  const baixaveis = embaralha([...br].filter((n) => !bred.has(n)));
  const pgFora = new Set(baixaveis.slice(0, nBr - nPg));
  const pg = new Set([...br].filter((n) => !pgFora.has(n)));
  const sc = [...bred].filter((n) => dataIA[n] <= ate28 || k < 4).length;   // IA com 28+ dias entra em taxa mesmo sem DG (fracasso); a de menos de 28 só se o resultado já é conhecido
  const L = (set) => [...set].sort(ordem);
  const taxa = (a, b) => (b ? Math.round((1000 * a) / b) / 10 : null);
  ciclos.push({
    ciclo: k + 1, inicio: inicioDe(k), fim: fimDe(k), br_elig: br.size, bred: bred.size, taxa_servico: taxa(bred.size, br.size),
    pg_elig: pg.size, preg: preg.size, taxa_prenhez: taxa(preg.size, pg.size), taxa_concepcao: taxa(preg.size, sc), servicos_com_resultado: sc,
    janela_dg_completa: janela(k), animais: { br_elig: L(br), bred: L(bred), pg_elig: L(pg), preg: L(preg) },
  });
}
// resumo: média ponderada pelo denominador de cada ciclo (como o backend, usando as taxas já arredondadas)
const pond = (campo, den) => { const t = ciclos.reduce((n, c) => n + c[den], 0); return t ? Math.round((10 * ciclos.reduce((n, c) => n + (c[campo] || 0) * c[den], 0)) / t) / 10 : null; };
const avaliados = new Set(ciclos.flatMap((c) => [...c.animais.br_elig, ...c.animais.bred, ...c.animais.pg_elig, ...c.animais.preg]));
export const respostaCiclos = () => ({
  ancora: HOJE, modo: "fim", categoria: "todas", periodo: { inicio: ciclos[0].inicio, fim: ciclos[N - 1].fim }, ciclos,
  resumo: { taxa_servico: pond("taxa_servico", "br_elig"), taxa_prenhez: pond("taxa_prenhez", "pg_elig"), taxa_concepcao: pond("taxa_concepcao", "servicos_com_resultado"),
    animais_avaliados: avaliados.size, animais_carregados: animais.filter((a) => a.sexo !== "M").length },
  metas: { taxa_servico: 60, taxa_prenhez: 20, taxa_concepcao: 35 },   // metas da fazenda (Parâmetros > Metas reprodutivas)
  parametros: { pev_dias: 50, dias_minimos_no_ciclo: 11, dias_resultado_conhecido: DIAS_RES },
  // texto idêntico ao do backend (reproducao.py::ciclos_de_21_dias)
  ressalva_historica: "A marcação \"a descartar\" passou a ser datada: quem for marcado de agora em diante sai do cálculo só a partir da data da marcação. Quem já estava marcado antes disso não tem data registrada e segue valendo para todo o período. Baixas sempre foram datadas e são reconstruídas corretamente.",
});
export async function t3e4(req, res, p, u, send) {
  if (p === "/reproducao/ciclos-21-dias" && req.method === "GET") return send(respostaCiclos());
  return false;
}
if (process.argv[1]?.endsWith("t3e4.mjs")) { const rr = respostaCiclos(); console.log(JSON.stringify({ ...rr, ciclos: rr.ciclos.map((c) => ({ ...c, animais: Object.fromEntries(Object.entries(c.animais).map(([k, v]) => [k, v.length])) })) }, null, 1)); }
