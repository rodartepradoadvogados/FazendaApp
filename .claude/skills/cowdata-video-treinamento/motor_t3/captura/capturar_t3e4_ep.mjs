// T3 · Ep. 4 (Ciclos de 21 dias — Menu › Reprodução) — telas REAIS do app em produção contra o stub (EP=t3e4), DPR 3 por padrão.
// Saída em shots_ep/: placas e Menu com Reprodução aberta (abertura 3D e item "Ciclos de 21 dias"), a tela Ciclos de 21 dias como PÁGINA ALTA
// (cabeçalho e barra escondidos; o motor rola a imagem por trás das barras reais), o detalhe de um ciclo (DetalheCiclo, também alto) e mapa.json
// com as caixas reais do DOM (px CSS; páginas altas em coordenadas do documento): rótulos, entradas, pílulas, botões Excel/PDF, os 3 cartões de resumo,
// os cartões de ciclo (barras Serviço/Prenhez, selo "em apuração", "(parcial)") e os quatro grupos do detalhe.
//   EP=t3e4 STUB_PORT=8400 node stub-api.mjs &   ·   next start -p 3400   →   STUB=8400 APP=3400 node capturar_t3e4_ep.mjs      DSF=1 para teste rápido
// O app em produção foi compilado com a API em localhost:8000: as chamadas são redirecionadas para a porta do stub por context.route.
import fs from "fs";
import { chromium, novoContexto, pagina } from "./lib.mjs";
const DSF = Number(process.env.DSF || 3), OUT = "shots_ep/"; fs.mkdirSync(OUT, { recursive: true });
const STUB = process.env.STUB || 8000, APPP = process.env.APP || 3000, API = `http://localhost:${STUB}`, APP = `http://localhost:${APPP}`;
const br = await chromium.launch({ args: ["--lang=pt-BR"], env: { ...process.env, LANGUAGE: "pt_BR", LC_ALL: "pt_BR.UTF-8", LANG: "pt_BR.UTF-8" } });
const ctx = await novoContexto(br, 844, DSF);
await ctx.addInitScript(() => {
  localStorage.setItem("usuario", JSON.stringify({ id: 1, nome: "Bernadete", papel: "admin", eh_dono: true, permissoes: [] }));
  const trocar = () => { for (const p of document.querySelectorAll("header p")) if (p.textContent.includes("Estreito Ponte de Pedra")) p.textContent = "Fazenda Boa Esperança"; };
  new MutationObserver(trocar).observe(document, { childList: true, subtree: true, characterData: true }); document.addEventListener("DOMContentLoaded", trocar);
  try { for (const k of Object.keys(localStorage)) if (k.startsWith("rascunho") || k.startsWith("mob_cache") || k.startsWith("menu_ciclos")) localStorage.removeItem(k); } catch {}
});
if (STUB != 8000) await ctx.route("http://localhost:8000/**", (r) => r.continue({ url: r.request().url().replace("localhost:8000", "localhost:" + STUB) }));
const p = await pagina(ctx); const esp = (ms = 700) => p.waitForTimeout(ms);
const mapa = { dsf: DSF }; const log = (...a) => console.log(...a);
const topo = async () => { await p.evaluate(() => { document.activeElement?.blur?.(); window.scrollTo(0, 0); document.body.scrollTo(0, 0); document.scrollingElement.scrollTo(0, 0); }); await esp(350); };

// ── caixas reais (px CSS, coordenadas do documento) ──
const coletar = () => p.evaluate(() => {
  const sy = window.scrollY, box = (r) => ({ x: +r.x.toFixed(2), y: +(r.y + sy).toFixed(2), w: +r.width.toFixed(2), h: +r.height.toFixed(2) });
  const R = (e) => (e ? box(e.getBoundingClientRect()) : null);
  const txt = (e) => (e?.innerText || "").replace(/\s+/g, " ").trim();
  // caixa de um trecho de texto dentro de um elemento (nó de texto → Range)
  const trecho = (el, re) => { if (!el) return null; const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT); let n; while ((n = w.nextNode())) { const m = n.textContent.match(re); if (m) { const rg = document.createRange(); rg.setStart(n, m.index); rg.setEnd(n, m.index + m[0].length); return box(rg.getBoundingClientRect()); } } return null; };
  // caixa do n-ésimo nó de texto não vazio de um elemento (o React separa "{num} / {den}" em três nós)
  const nodoTxt = (el, i) => { const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT), ns = []; let n; while ((n = w.nextNode())) if (/\d/.test(n.textContent)) ns.push(n); const t = ns.at(i); if (!t) return null; const rg = document.createRange(); rg.selectNodeContents(t); return box(rg.getBoundingClientRect()); };
  const o = { docH: Math.max(document.documentElement.scrollHeight, document.body.scrollHeight) };
  const hdr = document.querySelector("header"), nav = document.querySelector("nav.mob-nav");
  o.hdrBottom = hdr ? hdr.getBoundingClientRect().bottom : 0; o.navTop = nav ? nav.getBoundingClientRect().top : 844;
  o.voltar = R(document.querySelector('button[aria-label="Voltar"]')); o.titulo = R(document.querySelector("h1")); o.tituloTxt = txt(document.querySelector("h1"));
  o.pills = [...document.querySelectorAll(".mob-pill")].map((b) => ({ txt: txt(b), ativa: b.classList.contains("ativa"), ...R(b) }));
  o.labels = [...document.querySelectorAll("label")].map((l) => ({ txt: txt(l), ...R(l), span: R(l.querySelector("span")), input: R(l.querySelector("input")), valor: l.querySelector("input")?.value ?? null }));
  o.rotulos = [...document.querySelectorAll("span")].filter((e) => /^(Data de referência|Nº de ciclos|A data escolhida é o…|Categoria)$/.test(txt(e))).map((e) => ({ txt: txt(e), ...R(e) }));
  o.export = [...document.querySelectorAll("button[title^='Exportar']")].map((b) => ({ txt: txt(b), title: b.title, ...R(b) }));
  o.exportUniao = (() => { const bs = [...document.querySelectorAll("button[title^='Exportar']")]; if (!bs.length) return null; const rs = bs.map((b) => b.getBoundingClientRect()); const x0 = Math.min(...rs.map((r) => r.x)), y0 = Math.min(...rs.map((r) => r.y)), x1 = Math.max(...rs.map((r) => r.right)), y1 = Math.max(...rs.map((r) => r.bottom)); return box({ x: x0, y: y0, width: x1 - x0, height: y1 - y0 }); })();
  // cartões (resumo e ciclos): cada filho folha com texto, em ordem
  const folhas = (c) => [...c.querySelectorAll("*")].filter((e) => e.children.length === 0 && txt(e)).map((e) => ({ txt: txt(e), ...R(e), cor: getComputedStyle(e).color, fs: getComputedStyle(e).fontSize }));
  o.cards = [...document.querySelectorAll(".mob-card")].map((c) => ({ txt: txt(c), ...R(c), folhas: folhas(c),
    parcial: trecho(c, /\(parcial\)/), servico: trecho(c, /Serviço · [\d.]+%|Serviço · —/), prenhez: trecho(c, /Prenhez · [\d.]+%(?: \(parcial\))?/),
    barras: [...c.querySelectorAll("div")].filter((d) => d.children.length === 2 && d.children[0].children.length === 2 && d.children[0].children[0].tagName === "SPAN" && /^(Serviço|Prenhez) · /.test(txt(d.children[0].children[0]))).map((d) => ({ rotulo: txt(d.children[0].children[0]), contagem: txt(d.children[0].children[1]), linha: R(d.children[0]), rot: R(d.children[0].children[0]), cont: R(d.children[0].children[1]), num: nodoTxt(d.children[0].children[1], 0), den: nodoTxt(d.children[0].children[1], -1), trilha: R(d.children[1]), tudo: R(d) })),
    titulo: (() => { const t = [...c.querySelectorAll("span")].find((s) => /^Ciclo \d+$/.test(txt(s))); return R(t); })(),
    periodo: (() => { const t = [...c.querySelectorAll("span")].find((s) => /^\d{2}\/\d{2}\/\d{4} – /.test(txt(s))); return R(t); })(),
    selo: (() => { const t = [...c.querySelectorAll("span")].find((s) => txt(s) === "em apuração"); return R(t); })(),
  }));
  o.ps = [...document.querySelectorAll("p")].map((e) => ({ txt: txt(e), ...R(e), cor: getComputedStyle(e).color }));
  o.menu = [...document.querySelectorAll("button")].filter((b) => /Agenda Reprodutiva|Protocolos IATF|Ciclos de 21 dias|^Protocolos\b|Portal|Estoque|Recria/.test(txt(b).split("\n")[0])).map((b) => ({ txt: txt(b), ...R(b) }));
  o.heads = [...document.querySelectorAll("button[aria-expanded]")].map((b) => ({ txt: txt(b), aberta: b.getAttribute("aria-expanded"), ...R(b), pai: R(b.parentElement) }));
  return o;
});
// caixas dos quatro grupos (título + contagem + chips) — o motor contorna cada um
const grupos = async () => p.evaluate(() => {
  const sy = window.scrollY, box = (r) => ({ x: +r.x.toFixed(2), y: +(r.y + sy).toFixed(2), w: +r.width.toFixed(2), h: +r.height.toFixed(2) });
  const txt = (e) => (e?.innerText || "").replace(/\s+/g, " ").trim();
  return [...document.querySelectorAll(".mob-card")].map((c) => { const t = c.children[0], ch = c.children[1];
    return { txt: txt(t), card: box(c.getBoundingClientRect()), titulo: box(t.getBoundingClientRect()), chips: ch ? box(ch.getBoundingClientRect()) : null, nchips: ch ? ch.children.length : 0,
      contagem: (() => { const s = t.querySelector("span"); return s ? box(s.getBoundingClientRect()) : null; })(),
      tituloTxt: (() => { const w = document.createTreeWalker(t, NodeFilter.SHOW_TEXT); const n = w.nextNode(); if (!n) return null; const rg = document.createRange(); rg.selectNodeContents(n); const b = rg.getBoundingClientRect(); return box(b); })() }; });
});
// páginas altas: viewport = altura do documento, cabeçalho e barra escondidos (o motor rola a imagem por trás das barras reais)
async function alta(nome) {
  const estilo = await p.addStyleTag({ content: "header,nav.mob-nav{visibility:hidden!important}" });
  const H0 = await p.evaluate(() => Math.max(document.documentElement.scrollHeight, document.body.scrollHeight));
  await p.setViewportSize({ width: 390, height: Math.max(844, Math.min(H0, 5200)) }); await esp(900); await topo();
  const m = await coletar(); if (nome === "cd0") m.grupos = await grupos(); await p.screenshot({ path: OUT + nome + ".png" });
  await p.setViewportSize({ width: 390, height: 844 }); await esp(500);
  await estilo.evaluate((e) => e.remove()); await topo();
  mapa[nome] = m; log("alta", nome, "docH", m.docH);
}
const vp = async (nome) => { await p.screenshot({ path: OUT + nome + ".png" }); mapa[nome] = await coletar(); log("vp", nome); };

await fetch(API + "/__reset");
// ═══ 1) Menu: placas (abertura 3D) e Menu com Reprodução aberta (item "Ciclos de 21 dias") ═══
const COLAPSADAS = ["protocolos-restrito", "reproducao", "sanidade", "alimentacao", "producao", "gestao", "financeiro", "modulos", "administracao", "app"];
await p.goto(APP + "/app/menu", { waitUntil: "networkidle" }); await esp(1500);
await p.evaluate((c) => localStorage.setItem("mob_menu_secoes_colapsadas", JSON.stringify(c)), COLAPSADAS);
await p.reload({ waitUntil: "networkidle" }); await esp(1500);
const heads = await p.$$eval("button[aria-expanded]", (bs) => bs.map((b) => { const rr = (b.parentElement || b).getBoundingClientRect(); return { txt: b.innerText.replace(/\s+/g, " ").trim(), px: rr.x, py: rr.y, pw: rr.width, ph: rr.height }; }));
const nomes = ["reproducao", "sanidade", "alimentacao", "producao", "gestao", "financeiro"];
for (let i = 0; i < 6; i++) { const h = heads[i]; await p.screenshot({ path: OUT + `placa_${nomes[i]}.png`, clip: { x: h.px, y: h.py, width: h.pw, height: h.ph } }); }
mapa.heads = heads;
await p.locator("button[aria-expanded]", { hasText: "Reprodução" }).first().click(); await esp(900);
await p.screenshot({ path: OUT + "menu_repro.png" });
{ const r = await p.locator("button[aria-expanded]", { hasText: "Reprodução" }).first().evaluate((b) => { const r = b.parentElement.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; }); await p.screenshot({ path: OUT + "placa_reproducao_aberta.png", clip: { x: r.x, y: r.y, width: r.w, height: r.h } }); mapa.reproCard = r; }
mapa.menu_repro = await coletar(); log("menu_repro", JSON.stringify(mapa.menu_repro.menu.map((i) => [i.txt.slice(0, 22), Math.round(i.y)])), JSON.stringify(mapa.menu_repro.heads.map((h) => [h.txt.slice(0, 12), h.aberta, Math.round(h.y), Math.round(h.h)])));
// ═══ 2) Ciclos de 21 dias (toque no item do Menu) ═══
await p.evaluate(() => [...document.querySelectorAll("button")].find((x) => /^Ciclos de 21 dias/.test(x.innerText.trim())).click());
await p.waitForSelector("text=Serviço", { timeout: 15000 }); await esp(2200); await topo();
await p.screenshot({ path: OUT + "ci_vp.png" }); mapa.ci_vp = await coletar();
await alta("ci0");
// ═══ 3) Detalhe do ciclo 4 (o ciclo-exemplo, fechado): quatro grupos de vacas ═══
await p.locator(".mob-card", { hasText: "Ciclo 4" }).first().click(); await esp(1500); await topo();
await p.screenshot({ path: OUT + "cd_vp.png" }); mapa.cd_vp = await coletar();
await alta("cd0");
// ═══ 4) Volta (botão do app) ═══
await p.getByRole("button", { name: "Voltar" }).first().click(); await esp(1500); await topo();
await p.screenshot({ path: OUT + "ci_volta_vp.png" }); mapa.ci_volta_vp = await coletar();
fs.writeFileSync(OUT + "mapa.json", JSON.stringify(mapa, null, 1));
await br.close(); log("ok");
