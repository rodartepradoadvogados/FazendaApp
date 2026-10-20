// T3 · Ep. 3 — Baixa e aplicação do protocolo (Menu › Protocolos): dados fictícios + rotas do stub (EP=t3e3; herda t3e2/t3e1).
// Formatos idênticos aos de central_protocolos.py: GET /central-protocolos/acompanhamento|historico (_linha), GET /central-protocolos/{origem}/{id}
// (detalhe: dias[].hormonios[].opcoes[], animais[].celulas) e POST /central-protocolos/{origem}/{id}/baixa → {ok, avisos}.
// Data de referência 17/10/2026 (relógio fixo). Continuidade com o Ep. 2: o mesmo protocolo "IATF 3 MANEJOS" (D0 10/10, 6 vacas do 03 - Baixa).
// ATENÇÃO (fiel ao backend): "De qual lote?" só existe no protocolo SANITÁRIO (op["lotes"] só é preenchido para origem == "sanitario");
// IATF/Indução só oferecem a escolha do frasco. Por isso o frasco com 2 lotes abertos está no protocolo sanitário fictício (id 401).
import { animais } from "./dados.mjs";

const dia = (iso, n) => new Date(Date.parse(iso) + n * 864e5).toISOString().slice(0, 10);
const HOJE = "2026-10-17";
const f8 = (iso) => iso.slice(8, 10) + "/" + iso.slice(5, 7) + "/" + iso.slice(2, 4);
const sufixo = (d0, ultimo, nd) => `${f8(d0)} A ${f8(dia(d0, ultimo))} (D0 A D${ultimo} - ${nd} DIAS)`;

// ── IATF (continuidade do Ep. 2) ──
const D0_A = "2026-10-10", VACAS_A = ["3054", "3065", "3118", "3169", "3265", "3344"];
const SEM_D0 = "3169", JA_D7 = "3265";
const NOME_A = `IATF 3 MANEJOS - ${sufixo(D0_A, 11, 12)}`;
const PASSOS = [
  [0, "1.0 un Progesterona (dispositivo) + 2.0 ml Benzoato de estradiol + 2.5 ml GnRH", [["Progesterona (dispositivo)", 1, "un", "IM"], ["Benzoato de estradiol", 2, "ml", "IM"], ["GnRH", 2.5, "ml", "IM"]]],
  [7, "2.0 ml Prostaglandina", [["Prostaglandina", 2, "ml", "IM"]]],
  [9, "2.0 ml Prostaglandina + 1.0 ml Cipionato de estradiol", [["Prostaglandina", 2, "ml", "IM"], ["Cipionato de estradiol", 1, "ml", "IM"]]],
  [11, "Inseminação (IATF)", []],
];
// frascos REAIS do formato de estoque_baixa.opcoes_medicamento (nome do item de Estoque, saldo, unidade) — só princípio ativo, sem marca
const FRASCOS = { // estoque_id → [nome, saldo inicial, mínimo, unidade]
  11: ["Prostaglandina 50 ml", 46, 40, "ml"], 12: ["Prostaglandina 20 ml", 14, 10, "ml"],
  21: ["Ivermectina 500 ml", 320, 100, "ml"], 22: ["Ivermectina 100 ml", 60, 30, "ml"],
};
const saldo = {}; const zeraSaldo = () => { for (const [k, v] of Object.entries(FRASCOS)) saldo[k] = v[1]; };
zeraSaldo();
const opcao = (id, extra = {}) => ({ estoque_id: id, nome: FRASCOS[id][0], marca: null, saldo: saldo[id], unidade: FRASCOS[id][3], estoque_inicializado: true, sem_estoque: false, ...extra });
const OPCOES_IATF = { "Prostaglandina": [11, 12] };

let realizadasA, realizadasS;
const reset = () => {
  realizadasA = new Set(VACAS_A.filter((n) => n !== SEM_D0).map((n) => `${n}:0`)); realizadasA.add(`${JA_D7}:7`);
  realizadasS = new Set(BEZERRAS.flatMap((n) => [`${n}:0`])); zeraSaldo();
};

// ── Sanitário fictício (4 bezerras do 07 - Bezerras): D0 feito, D9 de hoje pendente ──
const BEZERRAS = animais.filter((a) => a.grupo_primario.startsWith("07")).slice(0, 4).map((a) => a.numero);
const D0_S = "2026-10-08";
const NOME_S = `VERMIFUGAÇÃO BEZERRAS - ${sufixo(D0_S, 9, 10)}`;
// ── Produtivo fictício (protocolo customizado de tipo "produtivo") ──
const D0_P = "2026-10-05";
const NOME_P = `MANEJO PRÉ-PARTO - ${sufixo(D0_P, 14, 15)}`;

const linha = (tipo, origem, id, nome, ini, fim, total, feitas, nAnim) => ({
  tipo, origem, origem_id: id, nome, data_inicio: ini, data_fim: fim, etapas_total: total, etapas_realizadas: feitas, etapas_faltam: total - feitas,
  animais: nAnim, status: "ativo", encerrado_em: null, encerrado_motivo: null,
});
const contaA = () => realizadasA.size;
const acompanhamento = () => [ // ordem do servidor: data_inicio decrescente
  linha("reprodutivo", "iatf", 301, NOME_A, D0_A, dia(D0_A, 11), 24, contaA(), 6),
  linha("sanitario", "sanitario", 401, NOME_S, D0_S, dia(D0_S, 9), 8, realizadasS.size, 4),
  linha("produtivo", "customizado", 501, NOME_P, D0_P, dia(D0_P, 14), 18, 12, 6),
];
const historico = () => [
  { ...linha("reprodutivo", "iatf", 302, `IATF 3 MANEJOS - ${sufixo("2026-09-26", 11, 12)}`, "2026-09-26", "2026-10-07", 16, 16, 4), status: "concluido" },
];

const celulaA = (n, d) => { const prev = dia(D0_A, d), real = realizadasA.has(`${n}:${d}`); return { dia: d, rotulo: "D" + d, data_prevista: prev, data_realizacao: real ? (real && (n === JA_D7 && d === 7 ? prev : dataBaixa.get(`${n}:${d}`) || prev)) : null, realizada: real, estado: real ? "realizada" : prev < HOJE ? "atrasada" : "pendente" }; };
const dataBaixa = new Map();
const detalheA = (incluir) => ({
  origem: "iatf", origem_id: 301, nome: NOME_A, data_inicio: D0_A, responsavel: null, observacao: null, encerrado_em: null, encerrado_motivo: null, ativo: true,
  etapas_total: 24, etapas_realizadas: contaA(), etapas_atrasadas: VACAS_A.filter((n) => !realizadasA.has(`${n}:0`)).length,
  dias: PASSOS.map(([d, desc, hs]) => ({
    dia: d, rotulo: "D" + d, data_prevista: dia(D0_A, d), descricao: desc, total: 6, realizadas: VACAS_A.filter((n) => realizadasA.has(`${n}:${d}`)).length,
    hormonios: hs.map(([produto, dose, unidade, via]) => ({ produto, dose, unidade, via, opcoes: (OPCOES_IATF[produto] || []).map((id) => opcao(id)) })),
  })),
  animais: VACAS_A.map((n) => ({ numero_matriz: n, celulas: PASSOS.map(([d]) => celulaA(n, d)) })),
});
const lotesIvermectina = [
  { id: 5, numero_lote: "2407", data_compra: "2026-07-12", quantidade_restante: 120 },
  { id: 6, numero_lote: "2609", data_compra: "2026-09-20", quantidade_restante: 200 },
];
const detalheS = () => ({
  origem: "sanitario", origem_id: 401, nome: NOME_S, data_inicio: D0_S, responsavel: null, observacao: null, encerrado_em: null, encerrado_motivo: null, ativo: true,
  etapas_total: 8, etapas_realizadas: realizadasS.size, etapas_atrasadas: 0,
  dias: [0, 9].map((d) => ({
    dia: d, rotulo: "D" + d, data_prevista: dia(D0_S, d), descricao: null, total: 4, realizadas: BEZERRAS.filter((n) => realizadasS.has(`${n}:${d}`)).length,
    hormonios: [{ produto: "Ivermectina", dose: 1, unidade: "ml", via: "SC", opcoes: [opcao(21, { lotes: lotesIvermectina }), opcao(22, { lotes: [{ id: 7, numero_lote: "2511", data_compra: "2026-05-04", quantidade_restante: 60 }] })] }],
  })),
  animais: BEZERRAS.map((n) => ({ numero_matriz: n, celulas: [0, 9].map((d) => { const prev = dia(D0_S, d), real = realizadasS.has(`${n}:${d}`); return { dia: d, rotulo: "D" + d, data_prevista: prev, data_realizacao: real ? prev : null, realizada: real, estado: real ? "realizada" : prev < HOJE ? "atrasada" : "pendente" }; }) })),
});

const fmtG = (x) => String(Math.round(x * 100) / 100);
export const cfg3 = { atrasoBaixa: 0 };
export const log3 = [];
reset();
export async function t3e3(req, res, p, u, send, corpo) {
  if (p === "/__reset") { reset(); dataBaixa.clear(); log3.length = 0; return false; } // também deixa o t3e1 reiniciar os cards
  if (p === "/__cfg3" && req.method === "POST") { Object.assign(cfg3, await corpo(req)); return send(cfg3); }
  if (p === "/__log3") return send(log3);
  if (p === "/central-protocolos/acompanhamento") { const t = u.searchParams.get("tipo"); return send(acompanhamento().filter((l) => !t || l.tipo === t)); }
  if (p === "/central-protocolos/historico") { const t = u.searchParams.get("tipo"); return send(historico().filter((l) => !t || l.tipo === t)); }
  if (p === "/central-protocolos/iatf/301" && req.method === "GET") return send(detalheA(u.searchParams.get("incluir_sem_estoque") === "true"));
  if (p === "/central-protocolos/sanitario/401" && req.method === "GET") return send(detalheS());
  const m = p.match(/^\/central-protocolos\/(iatf|sanitario)\/(301|401)\/baixa$/);
  if (m && req.method === "POST") {
    const b = await corpo(req); log3.push({ p, b });
    if (cfg3.atrasoBaixa) await new Promise((ok) => setTimeout(ok, cfg3.atrasoBaixa));
    const iatf = m[1] === "iatf", vacas = iatf ? VACAS_A : BEZERRAS, set = iatf ? realizadasA : realizadasS;
    if (iatf && b.dia === 11) return send({ detail: "Este é o dia de inseminação — não dá para confirmar por aqui. Registre o serviço em Reprodução › Inseminação (com touro/sêmen), que fecha esta etapa automaticamente." }, 400);
    const alvo = (b.animais || vacas).filter((n) => !set.has(`${n}:${b.dia}`));
    for (const n of alvo) { set.add(`${n}:${b.dia}`); dataBaixa.set(`${n}:${b.dia}`, b.data_realizacao || HOJE); }
    // estoque do frasco escolhido (dose × animais) e aviso REAL de rules/estoque_baixa.py::movimentar
    const avisos = [];
    for (const md of b.medicamentos || []) {
      const it = FRASCOS[md.estoque_id]; if (!it) continue;
      saldo[md.estoque_id] -= (md.dose || 0) * alvo.length;
      if (saldo[md.estoque_id] < 0) avisos.push(`Estoque de "${it[0]}" ficou negativo (saldo: ${fmtG(saldo[md.estoque_id])} ${it[3]}). Registre a entrada/compra que faltou.`);
      else if (saldo[md.estoque_id] < it[2]) avisos.push(`Estoque de "${it[0]}" ficou abaixo do mínimo (saldo: ${fmtG(saldo[md.estoque_id])}, mínimo: ${fmtG(it[2])} ${it[3]}).`);
    }
    return send({ ok: true, avisos });
  }
  return false;
}
