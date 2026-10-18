// API de mentira para filmar as telas reais (dados fictícios, Fazenda Boa Esperança). Aplica POST /movimentacoes/mover.
import http from "node:http";
import { animais, lotes, SEED_MOTIVOS, estadosEp2, candidatasEp3, DATA_REF, pesagensRel, secagemLista, ESTOQUE7 } from "./dados.mjs";
const EP7 = process.env.EP === "t2e7"; // Ep. 7: pesagem corporal e secagem (herda o Ep. 6)
const EP6 = process.env.EP === "t2e6" || EP7; // Ep. 6: controle leiteiro (herda o Ep. 5)
const EP5 = process.env.EP === "t2e5" || EP6; // Ep. 5: protocolo de IATF (herda o Ep. 4)
const EP4 = process.env.EP === "t2e4" || EP5; // Ep. 4: parto (herda o Ep. 3)
const EP3 = process.env.EP === "t2e3" || EP4; // Ep. 3: diagnóstico de gestação (usa também os estados e o estoque do Ep. 2)
const EP2 = process.env.EP === "t2e2" || EP3; // Ep. 2: inseminação em lote
const INICIAL = EP2 ? { est: structuredClone(estadosEp2), semen: structuredClone(globalThis.__SEMEN), cand: structuredClone(candidatasEp3) } : null;
const ANIMAIS0 = EP4 ? structuredClone(animais) : null; // Ep. 4: o parto acrescenta a cria à lista; /__reset volta ao início
const REL0 = EP7 ? structuredClone(pesagensRel) : null, SEC0 = EP7 ? structuredClone(secagemLista.animais) : null, EST0 = EP7 ? structuredClone(ESTOQUE7) : null; // Ep. 7: /__reset volta ao início
const cfg = { atraso: 0, falhar: [] }; // POST /__cfg {atraso: ms por envio, falhar: [brincos que falham 1 vez]}
const log = [];
const estadoDe = (a) => {
  const g = a.grupo_primario;
  if (EP2) { const x = estadosEp2[a.numero]; return { numero: a.numero, estado: x.estado, categoria: a.categoria_abrev, lote: g, del_dias: a.del_dias, data_ultimo_parto: null, dias_gestacao: x.gest || null, parto_previsto: null, data_servico: null, tipo_servico: null, protocolo: null, dias_desde_servico: x.ia ?? null, protocolo_dia_atual: x.prot ?? null, protocolo_d0: x.d0 ?? null }; }
  const e = { numero: a.numero, estado: "apta", categoria: a.categoria_abrev, lote: g, del_dias: a.del_dias, data_ultimo_parto: null, dias_gestacao: null, parto_previsto: null, data_servico: null, tipo_servico: null, protocolo: null, dias_desde_servico: null };
  if (g.startsWith("04") || g.startsWith("05")) { e.estado = "gestante"; e.dias_gestacao = 230; }
  else if (g.startsWith("06") || g.startsWith("07")) e.estado = "nao_apta";
  else { const k = Number(a.numero) % 5; e.estado = ["gestante","apta","inseminada","gestante","pev"][k]; if (k===0||k===3) e.dias_gestacao = 80 + (Number(a.numero)%120); }
  return e;
};
function corpo(req) { return new Promise((ok) => { let b = ""; req.on("data", (c) => (b += c)); req.on("end", () => { try { ok(b ? JSON.parse(b) : {}); } catch { ok({}); } }); }); }
http.createServer(async (req, res) => {
  const u = new URL(req.url, "http://x"); const p = u.pathname;
  res.setHeader("Access-Control-Allow-Origin", req.headers.origin || "*");
  res.setHeader("Access-Control-Allow-Headers", "authorization,content-type,idempotency-key");
  res.setHeader("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS");
  res.setHeader("Content-Type", "application/json");
  if (req.method === "OPTIONS") { res.statusCode = 204; return res.end(); }
  const send = (obj, status = 200) => { res.statusCode = status; res.end(JSON.stringify(obj)); };
  if (p === "/health") return send({ ok: true });
  if (p === "/agenda/") return send({ eventos: [] });
  if (p === "/agenda/materializar") return send({ ok: true });
  if (p === "/__log") return send(log);
  if (p === "/auth/me") return send({ papel: "admin", eh_dono: true, permissoes: [] });
  if (p === "/animais/") return send(animais);
  if (p === "/lotes/") return send(lotes);
  if (p === "/movimentacoes/motivos") return send(SEED_MOTIVOS);
  if (p === "/movimentacoes/sugestoes") return send({ total: 0, lotes_com_criterio: 0, sugestoes: [] });
  if (p === "/indicadores/estados-reprodutivos") return send({ data_referencia: "2026-10-17", animais: animais.map(estadoDe), contagem: {}, parametros: {} });
  if (EP4 && p === "/__reset") { animais.splice(0, animais.length, ...structuredClone(ANIMAIS0)); }
  if (EP7 && p === "/__reset") { pesagensRel.splice(0, pesagensRel.length, ...structuredClone(REL0)); secagemLista.animais.splice(0, secagemLista.animais.length, ...structuredClone(SEC0)); secagemLista.ultima_secagem = null; ESTOQUE7.splice(0, ESTOQUE7.length, ...structuredClone(EST0)); }
  if (EP2 && p === "/__reset") { for (const k of Object.keys(estadosEp2)) estadosEp2[k] = structuredClone(INICIAL.est[k]); globalThis.__SEMEN = structuredClone(INICIAL.semen); if (EP3) for (const k of Object.keys(candidatasEp3)) candidatasEp3[k] = structuredClone(INICIAL.cand[k]); cfg.atraso = 0; cfg.falhar = []; return send({ ok: true }); }
  if (EP4 && p === "/producao/sugestao-lote-evento" && req.method === "POST") { // mãe recém-parida → 01 - Alta; cria Bezerra → 07 - Bezerras
    const b = await corpo(req); log.push({ p, b });
    const cria = /^Bezerr/.test(b.categoria_abrev || "");
    return send({ lote_sugerido: cria ? { codigo: "07", nome: "Bezerras", rotulo: "07 - Bezerras" } : { codigo: "01", nome: "Alta", rotulo: "01 - Alta" } });
  }
  if (EP4 && p === "/reproducao/parto" && req.method === "POST") {
    const b = await corpo(req); log.push({ p, b });
    if (cfg.atraso) await new Promise((ok) => setTimeout(ok, cfg.atraso));
    const criadas = (b.crias || []).filter((c) => c.numero && c.nasceu_viva !== false).map((c) => c.numero);
    for (const c of b.crias || []) if (c.numero && !animais.some((a) => a.numero === c.numero)) animais.push({ numero: c.numero, nome: null, grupo_primario: null, categoria_abrev: c.sexo === "F" ? "Bezerra" : "Bezerro", categoria_completa: c.sexo === "F" ? "Bezerra" : "Bezerro", sexo: c.sexo, del_dias: null, eh_semen: false, raca: "Holandesa" });
    return send({ ok: true, numero_matriz: b.numero_matriz, crias_criadas: criadas });
  }
  if (EP4 && p === "/sanidade/colostragem" && req.method === "POST") { const b = await corpo(req); log.push({ p, b }); return send({ ok: true }); }
  if (p === "/__cfg" && req.method === "POST") { Object.assign(cfg, await corpo(req)); return send(cfg); }
  if (EP2 && p === "/cadastro/estoque-semen/disponivel") {
    const t = globalThis.__SEMEN.touros; const tot = (k) => t.filter((x) => x.tipo === k).reduce((n, x) => n + x.doses, 0);
    return send({ touros: t, totais: { convencional: tot("convencional"), sexado: tot("sexado") }, minimos: { convencional: 5, sexado: 3 }, abaixo_minimo: { convencional: false, sexado: false } });
  }
  if (EP2 && p === "/reproducao/protocolo-iatf/ativos") return send([]);
  if (EP7) { // Ep. 7: pesagem corporal e secagem
    if (p === "/producao/pesagens/relatorio") return send({ linhas: pesagensRel });
    if (p === "/producao/pesagens" && req.method === "POST") { // grava a nova "última pesagem" de cada animal
      const b = await corpo(req); log.push({ p, b });
      if (cfg.atraso) await new Promise((ok) => setTimeout(ok, cfg.atraso));
      for (const e of b.entradas || []) { const l = pesagensRel.find((x) => x.numero_matriz === e.numero_matriz); if (l) { l.ultima_data = b.data_pesagem; l.ultima_peso = e.peso_kg; l.num_pesagens++; } }
      return send({ ok: true, criados: (b.entradas || []).length });
    }
    if (p === "/producao/secagem-lista") return send(secagemLista);
    if (p === "/producao/secagem-info") { const l = secagemLista.animais.find((x) => x.numero_matriz === u.searchParams.get("numero_matriz")); return send(l ? { del_atual: l.del_atual, data_prevista_secagem: l.data_prevista_secagem, deve_secar: l.deve_secar, motivo_exclusao: null, dias_gestacao: l.dias_gestacao } : { del_atual: null, data_prevista_secagem: null, deve_secar: null, motivo_exclusao: null, dias_gestacao: null }); }
    if (p === "/producao/secagem" && req.method === "POST") { // sugere o 04 - Secas; a vaca sai da lista de lactação
      const b = await corpo(req); log.push({ p, b });
      if (cfg.atraso) await new Promise((ok) => setTimeout(ok, cfg.atraso));
      const i = secagemLista.animais.findIndex((x) => x.numero_matriz === b.numero_matriz); if (i >= 0) secagemLista.animais.splice(i, 1);
      secagemLista.ultima_secagem = b.data_secagem;
      for (const pr of b.produtos || []) { const it = ESTOQUE7.find((x) => x.nome === pr.produto); if (it && b.aplicado) it.quantidade -= pr.quantidade; }
      return send({ ok: true, lote_sugerido: { codigo: "04", nome: "Secas", rotulo: "04 - Secas" }, avisos: [] });
    }
    if (p === "/estoque/") return send({ itens: ESTOQUE7 });
    if (p === "/sanidade/aplicacoes") return send({ aplicacoes: [] });
    if (p === "/estoque/medicamentos") return send([]);
    if (p === "/cadastro/pessoas") return send([]);
    if (p === "/parametros/transferencia-lote-automatica") return send({ automatica: false });
  }
  if (EP6 && p === "/producao/controles" && req.method === "POST") { const b = await corpo(req); log.push({ p, b }); if (cfg.atraso) await new Promise((ok) => setTimeout(ok, cfg.atraso)); return send({ ok: true, criados: (b.entradas || []).length }); }
  if (EP5 && p === "/reproducao/protocolo-iatf" && req.method === "POST") { // Ep. 5: um único POST com o lote inteiro; as vacas passam a "em protocolo · D0"
    const b = await corpo(req); log.push({ p, b });
    if (cfg.atraso) await new Promise((ok) => setTimeout(ok, cfg.atraso));
    for (const n of b.animais || []) { const x = estadosEp2[n]; if (x) { x.estado = "em_protocolo"; x.prot = 0; x.d0 = b.data_d0; x.gest = null; x.ia = null; } }
    return send({ ok: true, protocolo: "IATF " + b.data_d0, animais: b.animais });
  }
  if (EP3 && p === "/reproducao/diagnostico/candidatas") {
    const c = candidatasEp3;
    return send({ data_referencia: DATA_REF, parametros: { dias_toque: 30, dias_reconfirmacao: 60 }, usa_adesivo: false, situacoes: c, totais: { a_tocar: c.a_tocar.length, a_reconfirmar: c.a_reconfirmar.length, reconfirmada: c.reconfirmada.length } });
  }
  if (EP3 && p === "/reproducao/diagnostico" && req.method === "POST") {
    const b = await corpo(req); log.push({ p, b });
    if (cfg.atraso) await new Promise((ok) => setTimeout(ok, cfg.atraso));
    const i = candidatasEp3.a_tocar.findIndex((x) => x.numero_matriz === b.numero_matriz);
    if (i < 0) return send({ detail: "stub: animal fora de A tocar" }, 422);
    const [it] = candidatasEp3.a_tocar.splice(i, 1); const x = estadosEp2[b.numero_matriz];
    if (b.resultado === "retoque") { // Positivo — para retoque: vai para "A reconfirmar"
      candidatasEp3.a_reconfirmar.push({ ...it, estado: "gestante", dias_gestacao: it.dias_desde_servico, fase: "a_reconfirmar", diagnostico: "POSITIVO", data_diagnostico: b.data_diagnostico, retoque: true, ainda_nao: false, dias_para_prazo: null, prazo_tipo: null });
      if (x) { x.estado = "gestante"; x.gest = it.dias_desde_servico; x.ia = null; }
    } else if (b.resultado === "negativo") { if (x) { x.estado = "apta"; x.ia = null; x.gest = null; } } // vira vazia e entra na Inseminação como apta
    else candidatasEp3.a_tocar.splice(i, 0, it);
    return send({ ok: true, numero_matriz: b.numero_matriz });
  }
  if (p === "/reproducao/agenda-reprodutiva/cards-config") return send({ cards: null, atualizado_em: null });
  if (EP2 && p === "/reproducao/servico" && req.method === "POST") {
    const b = await corpo(req); log.push({ p, b });
    if (cfg.atraso) await new Promise((ok) => setTimeout(ok, cfg.atraso));
    const i = cfg.falhar.indexOf(b.numero_matriz);
    if (i >= 0) { cfg.falhar.splice(i, 1); return send({}, 503); } // falha só na 1ª tentativa
    const x = estadosEp2[b.numero_matriz]; if (x) { x.estado = "inseminada"; x.ia = 0; x.gest = null; }
    const t = globalThis.__SEMEN.touros.find((y) => y.nome === b.reprodutor && y.tipo === b.tipo_semen); if (t && t.doses > 0) t.doses--;
    return send({ ok: true, numero_matriz: b.numero_matriz });
  }
  if (p === "/movimentacoes/mover" && req.method === "POST") {
    const b = await corpo(req); log.push({ p, b });
    const nao = (b.animais || []).filter((n) => !animais.some((a) => a.numero === n)); let movidos = 0;
    for (const n of b.animais || []) { const a = animais.find((x) => x.numero === n); if (a && !nao.includes(n)) { a.grupo_primario = lotes.find((l) => l.codigo === b.lote_destino_codigo)?.rotulo; movidos++; } }
    return send({ movidos, nao_encontrados: nao });
  }
  console.log("404", req.method, p);
  return send({ detail: "stub: não implementado " + p }, 404);
}).listen(8000, () => console.log("stub em 8000"));
