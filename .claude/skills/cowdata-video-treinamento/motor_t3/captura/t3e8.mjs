// T3 · Ep. 8 — Sanidade (Menu › Sanidade, módulo inteiro): dados fictícios + rotas do stub (EP=t3e8; herda t3e7…t3e1).
// Respostas no formato REAL dos endpoints (backend/fazenda/api/routers/sanitario/campo.py, routers/sanidade.py, rules/historico_sanitario.py), sem marca comercial de medicamento ou vacina
// (só princípio ativo / nome genérico). Hoje = 24/10/2026 (relógio fixo da captura); período padrão do app = 25/08 a 24/10/2026.
//   GET  /sanitario/campo/hoje                 → { hoje, dias:[Dia + quando("hoje"|"amanha") + atrasado + dias_atraso] }  (1 dia atrasado, 1 de hoje, 1 de amanhã)
//   GET  /sanitario/dias/{id}/pacote-offline   → { gerado_em, data_referencia, dia(+itens), caixas, estoques, veterinarios, animais, regras_aviso }
//   GET  /sanitario/leite-separado · /eu · /veterinarios · /conflitos · POST /dispositivos/heartbeat · /campo/sincronizar · /dias/{id}/ciencia
//   GET  /sanidade/aplicacoes                  → { aplicacoes:[…] } com data_inicio, data_fim, numeros, lotes, tipo, doencas (lote NA DATA da aplicação; chave c<id>/p<id>)
//   POST /sanidade/aplicacoes/{id}/cura        → marca curado / não curado (a lista seguinte devolve o valor gravado)
//   GET  /cadastro/doencas · /sanidade/indicacoes-doenca/{id} → Remédios por Doença (1ª escolha SEM estoque, 2ª com estoque, observação, dose/via/carência)
import { animais } from "./dados.mjs";

const HOJE = "2026-10-24", AGORA = "2026-10-24T10:05:00-03:00";
const dia = (iso, n) => new Date(Date.parse(iso + "T12:00:00Z") + n * 864e5).toISOString().slice(0, 10);
const dif = (a, b) => Math.round((Date.parse(a + "T12:00:00Z") - Date.parse(b + "T12:00:00Z")) / 864e5);
const cod = (rot) => (rot || "").split(" - ")[0].trim();
const lista = (u, k) => u.searchParams.getAll(k).flatMap((v) => v.split(",")).map((s) => s.trim()).filter(Boolean);
const grupo = (g) => animais.filter((a) => a.grupo_primario === g && a.sexo === "F" && !a.eh_semen).map((a) => a.numero);
const idDe = (numero) => 1000 + animais.findIndex((a) => a.numero === numero);

// ── cadastro de vacinas/exames (caixas) e estoque ──
const CAIXAS = {
  1: { caixa_id: 1, nome: "Vacina brucelose B19", nome_curto: "B19", tipo: "vacina", produto: { modo: "estoque", estoque_id: 201, texto: null, dose_valor: 2, dose_unidade: "mL", dose_x_kg: null } },
  2: { caixa_id: 2, nome: "Vacina clostridiose", nome_curto: "Clostridiose", tipo: "vacina", produto: { modo: "estoque", estoque_id: 202, texto: null, dose_valor: 5, dose_unidade: "mL", dose_x_kg: null } },
  3: { caixa_id: 3, nome: "Exame de tuberculose", nome_curto: "Tuberculose", tipo: "exame", produto: { modo: "nao_se_aplica", estoque_id: null, texto: null, dose_valor: null, dose_unidade: null, dose_x_kg: null } },
};
const ESTOQUES = [
  { id: 201, nome: "Vacina brucelose B19", unidade: "mL", saldo: 100 },
  { id: 202, nome: "Vacina clostridiose", unidade: "mL", saldo: 250 },
];
const VETS = [{ pessoa_id: 1, nome: "Dra. Ana", crmv: null }];

// ── os três dias: 1 atrasado (14/10), 1 de hoje (B19 em bezerras, 1 animal vendido) e 1 de amanhã (exame) ──
const NOVILHAS = grupo("06 - Novilhas").slice(0, 8), BEZERRAS = grupo("07 - Bezerras").slice(0, 6), MEDIA = grupo("02 - Média").slice(0, 12);
const VENDIDA = BEZERRAS[3];                                  // vendida: sai da fila sozinha (o servidor já a tirou da contagem)
const NA_FILA = BEZERRAS.filter((n) => n !== VENDIDA);        // 5 bezerras
const CATEG = (g) => ({ "06 - Novilhas": ["Novilha", "14 m"], "07 - Bezerras": ["Bezerra", "5 m"], "02 - Média": ["Vaca", "4 a 2 m"] }[g]);
const DIAS = [
  { id: 11, nome: "Vacina clostridiose", tipo: "vacina", data: "2026-10-14", hora: "07:30", caixa: 2, numeros: NOVILHAS, grupo: "06 - Novilhas", quando: "hoje", atrasado: true, dias_atraso: dif(HOJE, "2026-10-14") },
  { id: 12, nome: "Vacina brucelose B19", tipo: "vacina", data: HOJE, hora: "08:00", caixa: 1, numeros: NA_FILA, grupo: "07 - Bezerras", quando: "hoje", saidos: [{ animal_id: idDe(VENDIDA), numero: VENDIDA, motivo: "venda", data_baixa: "2026-10-22" }] },
  { id: 13, nome: "Exame de tuberculose", tipo: "exame", data: "2026-10-25", hora: "07:00", caixa: 3, numeros: MEDIA, grupo: "02 - Média", quando: "amanha" },
];
const diaOut = (d, comItens = false) => {
  const cx = CAIXAS[d.caixa], n = d.numeros.length, saidos = d.saidos || [];
  const o = { id: d.id, nome: d.nome, tipo: d.tipo, data: d.data, hora: d.hora, data_prevista: d.data, estado: "marcado", veterinario: { pessoa_id: 1, texto: "Dra. Ana", crmv: null }, observacao: null, decisao_riscos: null,
    versao_lock: 1, fechado_em: null, fechamento_auto: false, motivo_cancelamento: null,
    caixas: [{ caixa_id: cx.caixa_id, nome: cx.nome, nome_curto: cx.nome_curto, tipo: cx.tipo, caixa_versao_id: cx.caixa_id, produto: cx.produto, carencia_decisao: null }],
    contagens: { animais: n, pendentes: n, feitos: 0, registros_apos_fechamento: 0, saidos: saidos.length || undefined } };
  if (saidos.length) o.saidos = saidos;
  if (comItens) o.itens = d.numeros.map((num, i) => ({ id: d.id * 100 + i, animal_id: idDe(num), numero: num, caixa_id: cx.caixa_id, origem: "janela", estado: "pendente", consentimento_log_id: null, registro_id: null }));
  return o;
};
const campoHoje = () => ({ hoje: HOJE, dias: DIAS.map((d) => ({ ...diaOut(d), quando: d.quando, ...(d.atrasado ? { atrasado: true, dias_atraso: d.dias_atraso } : {}) })) });
const pacote = (d) => {
  const cx = CAIXAS[d.caixa], [categ, idade] = CATEG(d.grupo);
  return { gerado_em: AGORA, data_referencia: HOJE, dia: diaOut(d, true), caixas: [{ ...cx, produto: cx.produto, regras: {} }], estoques: ESTOQUES, veterinarios: VETS,
    animais: d.numeros.map((num) => ({ animal_id: idDe(num), brinco: num, categoria: categ, lote: d.grupo, idade, peso: null, caixas: { [cx.caixa_id]: { elegivel: true, motivo: null, kind: null } } })),
    regras_aviso: { consentimento_fora_da_regra: true, desfazer_segundos: 60, aviso_offline_horas: 24, texto_consentimento: "" } };
};

// ── Histórico de tratamentos e vacinas (curativo + preventivo), período 25/08–24/10/2026, lotes 01/02/05 NA DATA ──
const G01 = grupo("01 - Alta"), G02 = grupo("02 - Média"), G05 = grupo("05 - Pré-parto");
const L = { "01": "01 - Alta", "02": "02 - Média", "05": "05 - Pré-parto" };
const CAR = (leite, carne, d) => ({ leite_dias: leite, carne_dias: carne, proibido_lactacao: false, texto: `Carência: leite — ${leite} dias / carne — ${carne} dias`,
  liberacao_leite: dia(d, leite), liberacao_carne: dia(d, carne), carencia_origem: "marca" });
const DOENCAS = [["Mastite clínica", "doenca"], ["Pneumonia", "doenca"], ["Metrite", "doenca"], ["Diarreia", "doenca"], ["Laminite", "doenca"], ["Retenção de placenta", "doenca"], ["Tristeza parasitária", "doenca"]]
  .map(([nome, tipo], i) => ({ id: i + 1, nome, tipo, ativo: true }));
const curativo = (id, data, num, lote, produto, dose, resp, carencia, doencaId, curada) => ({ id, chave: `c${id}`, tipo_historico: "curativo", numero: num, raca: "Holandesa", produto, categoria: "Antibiótico", dose, unidade: "mL", via: "Intramuscular",
  responsavel: resp, atividade: null, obs: null, ordem_parto: null, lote: L[lote], categoria_animal: "Vaca", natureza: "curativo", data, ano: 2026, mes: data.slice(0, 7), usuario_nome: "Zé", carencia,
  doenca_id: doencaId, doenca: DOENCAS[doencaId - 1].nome, curada, lote_na_data: L[lote], lote_fonte: "dia" });
const preventivo = (id, data, num, lote, caixa, produto, dose, resp) => ({ id, registro_id: id, chave: `p${id}`, tipo_historico: "preventivo", numero: num, animal_ativo: true, produto: `${caixa} — ${produto}`, caixa, categoria: "Vacina", dose, unidade: "mL", via: null,
  responsavel: resp, obs: null, natureza: "preventivo", data, ano: 2026, mes: data.slice(0, 7), usuario_nome: "Zé", carencia: null, doenca_id: null, doenca: null, curada: null, raca: "Holandesa", atividade: null, ordem_parto: null,
  lote: L[lote], categoria_animal: "Vaca", lote_na_data: L[lote], lote_fonte: "dia" });
const HIST0 = [
  preventivo(2001, "2026-10-23", G05[0], "05", "Clostridiose", "Vacina clostridiose", 5, "Zé"),
  preventivo(2002, "2026-10-23", G05[1], "05", "Clostridiose", "Vacina clostridiose", 5, "Zé"),
  curativo(1, "2026-10-22", G01[0], "01", "Ceftiofur", 12, "Dra. Ana", CAR(3, 8, "2026-10-22"), 1, null),
  curativo(2, "2026-10-20", G02[0], "02", "Gentamicina", 20, "Zé", CAR(4, 28, "2026-10-20"), 1, true),
  curativo(3, "2026-10-18", G02[1], "02", "Oxitetraciclina", 20, "Dra. Ana", CAR(3, 28, "2026-10-18"), 2, null),
  preventivo(2003, "2026-10-16", G01[1], "01", "Leptospirose", "Vacina leptospirose", 2, "Zé"),
  curativo(4, "2026-10-15", G01[1], "01", "Ceftiofur", 12, "Dra. Ana", CAR(3, 8, "2026-10-15"), 1, true),
  curativo(5, "2026-10-12", G02[2], "02", "Gentamicina", 20, "Zé", CAR(4, 28, "2026-10-12"), 1, false),
  preventivo(2004, "2026-10-10", G02[3], "02", "Clostridiose", "Vacina clostridiose", 5, "Zé"),
  curativo(6, "2026-10-09", G05[2], "05", "Oxitetraciclina", 20, "Dra. Ana", CAR(3, 28, "2026-10-09"), 2, true),
  curativo(7, "2026-10-02", G01[2], "01", "Ceftiofur", 12, "Dra. Ana", CAR(3, 8, "2026-10-02"), 1, true),
  preventivo(2005, "2026-09-26", G01[3], "01", "Leptospirose", "Vacina leptospirose", 2, "Zé"),
  curativo(8, "2026-09-28", G02[4], "02", "Ceftiofur", 12, "Dra. Ana", CAR(3, 8, "2026-09-28"), 1, true),
  preventivo(2006, "2026-09-19", G05[3], "05", "Clostridiose", "Vacina clostridiose", 5, "Zé"),
  curativo(9, "2026-09-15", G05[4], "05", "Oxitetraciclina", 20, "Dra. Ana", CAR(3, 28, "2026-09-15"), 2, true),
  preventivo(2007, "2026-09-12", G02[5], "02", "Clostridiose", "Vacina clostridiose", 5, "Zé"),
];
let HIST = structuredClone(HIST0);
const ordemHist = (a, b) => (a.data < b.data ? 1 : a.data > b.data ? -1 : a.id - b.id);
function aplicacoes(u) {
  const di = u.searchParams.get("data_inicio"), df = u.searchParams.get("data_fim"), tipo = u.searchParams.get("tipo"), nums = lista(u, "numeros"), lotes = lista(u, "lotes"), docs = lista(u, "doencas").map(Number);
  if (di && df && di > df) return { erro: "Período inválido: a data inicial é depois da final." };
  const rs = HIST.filter((r) => (!di || r.data >= di) && (!df || r.data <= df) && (!nums.length || nums.includes(r.numero)) && (!lotes.length || lotes.includes(cod(r.lote_na_data)))
    && (!tipo || tipo === "todos" || r.tipo_historico === tipo) && (!docs.length || docs.includes(r.doenca_id))).sort(ordemHist);
  return { aplicacoes: rs };
}

// ── leite separado: animais em carência de leite hoje (a partir dos curativos acima) ──
const leiteSeparado = () => { const itens = HIST.filter((r) => r.tipo_historico === "curativo" && r.carencia?.liberacao_leite && r.carencia.liberacao_leite >= HOJE)
  .map((r) => ({ origem: "curativo", numero: r.numero, animal_id: idDe(r.numero), produto: r.produto, caixa: null, data_aplicacao: r.data, liberacao_leite: r.carencia.liberacao_leite, modo: "descarte", sanidade_id: r.id }));
  return { hoje: HOJE, animais: new Set(itens.map((i) => i.numero)).size, itens }; };

// ── Remédios por Doença: Mastite clínica — 1ª escolha SEM estoque, 2ª com estoque (aviso), observação, dose/via/carência. Nomes genéricos, sem marca ──
const OPCOES_MASTITE = [
  { principio_ativo_id: 1, nome: "Ceftiofur", classificacao: "Antibiótico", prioridade: 1, status_estoque: "out", total_apresentacoes: 0, unidade_apresentacao: "frasco", marcas: [], nota: "Seguir o tempo de tratamento do protocolo da fazenda.", apresentacoes_cadastradas: 1,
    bulas: [{ marca: "Ceftiofur 5% injetável (frasco 100 mL)", laboratorio: null, dose: "1 mL para cada 50 kg", via: "Intramuscular", carencia: "Carência: leite — 3 dias / carne — 8 dias", em_estoque: false }] },
  { principio_ativo_id: 2, nome: "Gentamicina", classificacao: "Antibiótico", prioridade: 2, status_estoque: "ok", total_apresentacoes: 6, unidade_apresentacao: "frasco", marcas: [], nota: "Confirmar a dose com o veterinário.", apresentacoes_cadastradas: 1,
    bulas: [{ marca: "Gentamicina 10% injetável (frasco 100 mL)", laboratorio: null, dose: "1 mL para cada 20 kg", via: "Intramuscular", carencia: "Carência: leite — 4 dias / carne — 28 dias", em_estoque: true }] },
  { principio_ativo_id: 3, nome: "Meloxicam", classificacao: "Anti-inflamatório", prioridade: 3, status_estoque: "low", total_apresentacoes: 1, unidade_apresentacao: "frasco", marcas: [], nota: "Apoio ao antibiótico, contra a dor e a febre.", apresentacoes_cadastradas: 1,
    bulas: [{ marca: "Meloxicam 2% injetável (frasco 50 mL)", laboratorio: null, dose: "2,5 mL para cada 100 kg", via: "Intravenosa", carencia: "Carência: leite — 0 dias / carne — 15 dias", em_estoque: true }] },
];

export async function t3e8(req, res, p, u, send, corpo) {
  if (p === "/__reset") { HIST = structuredClone(HIST0); return false; }
  let m;
  if (req.method === "GET") {
    if (p === "/sanitario/campo/hoje") return send(campoHoje());
    if ((m = p.match(/^\/sanitario\/dias\/(\d+)\/pacote-offline$/))) { const d = DIAS.find((x) => x.id === Number(m[1])); return d ? send(pacote(d)) : send({ detail: "dia não encontrado" }, 404); }
    if (p === "/sanitario/leite-separado") return send(leiteSeparado());
    if (p === "/sanitario/eu") return send({ usuario_id: 1, administrador: true, veterinario_pessoa_id: null, pode: { cadastrar_caixa: true, aceitar_carencia: true, decidir_carencia: true, estornar: true, lancar: true, ler_exame: true, resolver_notas_admin: true } });
    if (p === "/sanitario/veterinarios") return send({ pessoas: VETS, aceita_texto_livre: true });
    if (p === "/sanitario/conflitos") return send([]);
    if (p === "/sanidade/aplicacoes") { const r = aplicacoes(u); return r.erro ? send({ detail: r.erro }, 400) : send(r); }
    if (p === "/cadastro/doencas") return send(DOENCAS);
    if ((m = p.match(/^\/sanidade\/indicacoes-doenca\/(\d+)$/))) { const id = Number(m[1]), d = DOENCAS.find((x) => x.id === id); return send({ doenca_id: id, doenca: d?.nome ?? "", opcoes: id === 1 ? OPCOES_MASTITE : [] }); }
    if (p === "/cadastro/pessoas") return send([{ id: 1, nome: "Zé", ativo: true }, { id: 2, nome: "Dra. Ana", ativo: true }]);
  }
  if (req.method === "POST") {
    if (p === "/sanitario/dispositivos/heartbeat") { const b = await corpo(req); return send({ id: 1, dispositivo_uid: b.dispositivo_uid, nome: b.nome ?? null, usuario_id: 1, ultimo_contato_em: AGORA, fila_pendentes: b.fila_pendentes ?? 0, fila_mais_antigo_em: null, aviso_admin_em: null }); }
    if (p === "/sanitario/campo/sincronizar") { const b = await corpo(req); const regs = b.registros || [];
      return send({ dispositivo_id: 1, gravados: regs.length, duplicados: 0, pendentes: 0, conflitos: 0, erros: 0,
        itens: regs.map((r, i) => ({ indice: i, status: "gravado", registro_id: 9000 + i, animal_id: r.animal_id ?? null, numero: r.numero_animal ?? null, caixa_id: r.caixa_id ?? null, avisos: [], requer: [], chave_idempotencia: r.chave_idempotencia ?? null })) }); }
    if (/^\/sanitario\/dias\/\d+\/ciencia$/.test(p)) { await corpo(req); return send({ ok: true }); }
    if ((m = p.match(/^\/sanidade\/aplicacoes\/(\d+)\/cura$/))) { const b = await corpo(req); const r = HIST.find((x) => x.id === Number(m[1]) && x.tipo_historico === "curativo"); if (!r) return send({ detail: "aplicação não encontrada" }, 404); r.curada = !!b.curada; return send({ id: r.id, curada: r.curada }); }
  }
  return false;
}
if (process.argv[1]?.endsWith("t3e8.mjs")) {
  const U = (q) => new URL("http://x/?" + q);
  console.log("dias", JSON.stringify(campoHoje().dias.map((d) => [d.id, d.nome, d.data, d.quando, d.atrasado, d.dias_atraso, d.contagens])));
  console.log("bezerras", JSON.stringify(BEZERRAS), "vendida", VENDIDA, "novilhas", NOVILHAS.length, "media", MEDIA.length);
  const h = aplicacoes(U("data_inicio=2026-08-25&data_fim=2026-10-24&tipo=todos")).aplicacoes;
  console.log("histórico", h.length, "animais", new Set(h.map((r) => r.numero)).size, "curativos", h.filter((r) => r.tipo_historico === "curativo").length);
  console.log("lotes 01+02", aplicacoes(U("lotes=01&lotes=02&tipo=todos")).aplicacoes.length, "doença 1", aplicacoes(U("doencas=1&tipo=todos")).aplicacoes.length);
  console.log("leite", JSON.stringify(leiteSeparado()));
}
