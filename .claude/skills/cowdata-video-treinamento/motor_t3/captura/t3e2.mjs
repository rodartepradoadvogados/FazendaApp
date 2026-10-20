// T3 · Ep. 2 — Protocolos IATF em andamento: dados fictícios + rotas do stub (EP=t3e2; herda t3e1). Data de referência 17/10/2026.
// Formato idêntico ao de GET /reproducao/protocolo-iatf/ativos (reproducao.py::listar_protocolos_iatf_ativos) e de GET /central-protocolos/iatf/{id}.
// Nomes dos lançamentos = nomenclatura real (rules/nomenclatura_protocolo.py::gerar_nome_lancamento: NOME DO MOLDE EM CAIXA ALTA - dd/mm/aa A dd/mm/aa (D0 A D11 - 12 DIAS)).
const dia = (iso, n) => new Date(Date.parse(iso) + n * 864e5).toISOString().slice(0, 10);
const HOJE = "2026-10-17", INTERVALO_VISITA = 21; // parâmetro intervalo_visita_reprodutiva (rules/parametros.py, padrão 21 dias)
const sufixo = (d0) => { const f = (iso) => iso.slice(8, 10) + "/" + iso.slice(5, 7) + "/" + iso.slice(2, 4); return `${f(d0)} A ${f(dia(d0, 11))} (D0 A D11 - 12 DIAS)`; };
const D0_A = "2026-10-10", D0_B = "2026-09-26";
const NOME_A = `IATF 3 MANEJOS - ${sufixo(D0_A)}`, NOME_B = `IATF 3 MANEJOS - ${sufixo(D0_B)}`;
// Em andamento: 6 vacas do 03 - Baixa (ordem numérica, como o servidor). 3169 sem baixa do D0 (selo âmbar); 3265 já teve a baixa do D7 hoje → próxima etapa D9.
const VACAS_A = ["3054", "3065", "3118", "3169", "3265", "3344"];
const SEM_D0 = "3169", JA_D7 = "3265";
const PASSOS = [[0, "1.0 un Progesterona (dispositivo) + 2.0 ml Benzoato de estradiol + 2.5 ml GnRH"], [7, "2.0 ml Prostaglandina"], [9, "2.0 ml Prostaglandina + 1.0 ml Cipionato de estradiol"], [11, "Inseminação (IATF)"]];
const animaisA = VACAS_A.map((n) => {
  const d0 = n !== SEM_D0, d7 = n === JA_D7;
  const proximo = !d0 ? null : d7 ? 9 : 7; // a etapa vem pela DATA: primeira pendente ainda não vencida (hoje <= data_prevista)
  const prim = n === SEM_D0 ? 7 : proximo;
  return { numero_matriz: n, etapa_atual: "D" + prim, data_etapa_atual: dia(D0_A, prim), d0_confirmado: d0, tem_etapa_confirmada: d0, pronta_para_inseminar: false };
});
const CANDIDATAS = [ // formato de selecionar_candidatas_iatf (herd-wide, ordenadas por número); motivos reais de rules/iatf.py
  { numero_matriz: "1045", sit_rep: "Vaz. atr.", del_dias: 187, motivo: "Vazia em atraso", estado: "atrasada", estado_rotulo: "Vazia atrasada" },
  { numero_matriz: "2127", sit_rep: "Vaz. apt.", del_dias: 176, motivo: "Vazia apta", estado: "apta", estado_rotulo: "Vazia apta" },
  { numero_matriz: "2371", sit_rep: "Vaz. apt.", del_dias: 63, motivo: "Diagnóstico negativo", estado: "apta", estado_rotulo: "Vazia apta" },
  { numero_matriz: "3990", sit_rep: "Vaz. atr.", del_dias: 201, motivo: "Vazia em atraso", estado: "atrasada", estado_rotulo: "Vazia atrasada" },
];
const ativos = [
  { lancamento_id: 301, nome_protocolo: NOME_A, data_d0: D0_A, animais: animaisA, concluido: false },
  { lancamento_id: 302, nome_protocolo: NOME_B, data_d0: D0_B, animais: [], concluido: true, data_d11: dia(D0_B, 11), proxima_visita: dia(dia(D0_B, 11), INTERVALO_VISITA), candidatas_proxima_visita: CANDIDATAS },
];
const detalheA = () => ({
  origem: "iatf", origem_id: 301, nome: NOME_A, data_inicio: D0_A, responsavel: null, encerrado_em: null, encerrado_motivo: null, ativo: true,
  etapas_total: 24, etapas_realizadas: 6, etapas_atrasadas: 1,
  dias: PASSOS.map(([d, desc]) => ({ dia: d, rotulo: "D" + d, data_prevista: dia(D0_A, d), descricao: desc, total: 6, realizadas: d === 0 ? 5 : d === 7 ? 1 : 0, hormonios: [] })),
  animais: VACAS_A.map((n) => ({ numero_matriz: n, celulas: PASSOS.map(([d]) => {
    const real = (d === 0 && n !== SEM_D0) || (d === 7 && n === JA_D7); const prev = dia(D0_A, d);
    return { dia: d, rotulo: "D" + d, data_prevista: prev, data_realizacao: real ? prev : null, realizada: real, estado: real ? "realizada" : prev < HOJE ? "atrasada" : "pendente" };
  }) })),
});
export const cfg2 = { atrasoDetalhe: 0 };
export async function t3e2(req, res, p, u, send, corpo) {
  if (p === "/__cfg2" && req.method === "POST") { Object.assign(cfg2, await corpo(req)); return send(cfg2); }
  if (p === "/reproducao/protocolo-iatf/ativos") return send(ativos);
  if (p === "/central-protocolos/iatf/301") { if (cfg2.atrasoDetalhe) await new Promise((ok) => setTimeout(ok, cfg2.atrasoDetalhe)); return send(detalheA()); }
  return false;
}
