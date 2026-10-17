// API de mentira para filmar as telas reais (dados fictícios, Fazenda Boa Esperança). Aplica POST /movimentacoes/mover.
import http from "node:http";
import { animais, lotes, SEED_MOTIVOS } from "./dados.mjs";
const log = [];
const estadoDe = (a) => {
  const g = a.grupo_primario;
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
  if (p === "/movimentacoes/mover" && req.method === "POST") {
    const b = await corpo(req); log.push({ p, b });
    const nao = (b.animais || []).filter((n) => !animais.some((a) => a.numero === n)); let movidos = 0;
    for (const n of b.animais || []) { const a = animais.find((x) => x.numero === n); if (a && !nao.includes(n)) { a.grupo_primario = lotes.find((l) => l.codigo === b.lote_destino_codigo)?.rotulo; movidos++; } }
    return send({ movidos, nao_encontrados: nao });
  }
  console.log("404", req.method, p);
  return send({ detail: "stub: não implementado " + p }, 404);
}).listen(8000, () => console.log("stub em 8000"));
