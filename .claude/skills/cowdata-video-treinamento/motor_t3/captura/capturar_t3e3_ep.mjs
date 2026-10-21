// T3 · Ep. 3 (Baixa e aplicação do protocolo — Menu › Protocolos) — telas REAIS do app em produção contra o stub (EP=t3e3), DPR 3 por padrão.
// Saída em shots_ep/: placas e Menu (abertura 3D), Menu com "Módulos" aberto (item Protocolos), páginas ALTAS (cabeçalho e barra escondidos; o motor
// rola a imagem por trás das barras reais): lista "Em andamento", detalhe do IATF (cartões D0/D7/D9/D11), formulário de baixa em cada estado
// (5 de 5, 4 de 5, lista de frascos aberta, frasco escolhido), detalhe depois da baixa (aviso de estoque), baixa do protocolo SANITÁRIO (frasco + lote)
// e mapa.json com as caixas reais do DOM (px CSS; páginas altas em coordenadas do documento).
//   EP=t3e3 STUB_PORT=8300 node stub-api.mjs &   ·   next start -p 3300   →   STUB=8300 APP=3300 node capturar_t3e3_ep.mjs      DSF=1 para teste rápido
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
  try { for (const k of Object.keys(localStorage)) if (k.startsWith("rascunho") || k.startsWith("mob_cache")) localStorage.removeItem(k); } catch {}
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
  const o = { docH: Math.max(document.documentElement.scrollHeight, document.body.scrollHeight) };
  const hdr = document.querySelector("header"), nav = document.querySelector("nav.mob-nav");
  o.hdrBottom = hdr ? hdr.getBoundingClientRect().bottom : 0; o.navTop = nav ? nav.getBoundingClientRect().top : 844;
  o.voltar = R(document.querySelector('button[aria-label="Voltar"]')); o.titulo = R(document.querySelector("h1"));
  o.pills = [...document.querySelectorAll(".mob-pill")].map((b) => ({ txt: txt(b), ativa: b.classList.contains("ativa"), ...R(b) }));
  o.cards = [...document.querySelectorAll(".mob-card")].map((c) => ({
    txt: txt(c), ...R(c),
    kids: [...c.children].map((k) => ({ txt: txt(k), ...R(k), spans: [...k.children].map((s) => ({ txt: txt(s), ...R(s) })), cor: getComputedStyle(k).color, fs: getComputedStyle(k).fontSize })),
    dose: trecho(c, /^[\d.]+ (ml|un)\b/), via: trecho(c, /\b(IM|SC|IV)$/),
    nota: trecho(c, /Lançar › Inseminação/), notaTxt: trecho(c, /A inseminação não se confirma aqui/),
  }));
  o.resumo = (() => { const e = [...document.querySelectorAll("div")].find((d) => /^\d+ de \d+ etapas/.test(txt(d)) && d.children.length <= 3 && d.querySelector("strong")); return e ? { txt: txt(e), ...R(e) } : null; })();
  o.folha = R([...document.querySelectorAll("button")].find((b) => /Folha de campo/.test(b.textContent)));
  o.ps = [...document.querySelectorAll("p")].map((e) => ({ txt: txt(e), ...R(e), cor: getComputedStyle(e).color }));
  o.labels = [...document.querySelectorAll("label")].map((l) => ({ txt: txt(l), ...R(l), check: l.querySelector('input[type="checkbox"]') ? { ...R(l.querySelector('input[type="checkbox"]')), on: l.querySelector('input[type="checkbox"]').checked } : null }));
  o.inputs = [...document.querySelectorAll("input")].map((i) => ({ tipo: i.type, valor: i.value, ...R(i) }));
  o.selects = [...document.querySelectorAll("select")].map((s) => ({ ...R(s), idx: s.selectedIndex, size: s.size, opts: [...s.options].map((op) => ({ txt: op.text, ...R(op) })) }));
  o.btns = [...document.querySelectorAll("button.mob-btn")].map((b) => ({ txt: txt(b), ...R(b), tn: (() => { const t = [...b.childNodes].filter((n) => n.nodeType === 3 && n.textContent.trim()).pop(); if (!t) return null; const rg = document.createRange(); rg.selectNodeContents(t); return box(rg.getBoundingClientRect()); })() }));
  const achar = (re) => { const el = [...document.querySelectorAll("div,p,span")].filter((e) => re.test(txt(e)) && [...e.children].every((c) => !re.test(txt(c)))).pop(); return el ? { txt: txt(el), ...R(el) } : null; };
  o.oQue = achar(/^O que aplicar neste dia$/); o.dataReal = achar(/^A data real da aplicação/);
  o.menu = [...document.querySelectorAll("button")].filter((b) => /Agenda Reprodutiva|Protocolos IATF|Ciclos de 21 dias|^Protocolos\b|Portal|Estoque|Recria/.test(txt(b).split("\n")[0])).map((b) => ({ txt: txt(b), ...R(b) }));
  return o;
});
// páginas altas: viewport = altura do documento, cabeçalho e barra escondidos (o motor rola a imagem por trás das barras reais)
async function alta(nome) {
  const estilo = await p.addStyleTag({ content: "header,nav.mob-nav{visibility:hidden!important}" });
  const H0 = await p.evaluate(() => Math.max(document.documentElement.scrollHeight, document.body.scrollHeight));
  await p.setViewportSize({ width: 390, height: Math.max(844, Math.min(H0, 5200)) }); await esp(900); await topo();
  const m = await coletar(); await p.screenshot({ path: OUT + nome + ".png" });
  await p.setViewportSize({ width: 390, height: 844 }); await esp(500);
  await estilo.evaluate((e) => e.remove()); await topo();
  mapa[nome] = m; log("alta", nome, "docH", m.docH);
}
const vp = async (nome) => { await p.screenshot({ path: OUT + nome + ".png" }); mapa[nome] = await coletar(); log("vp", nome); };

await fetch(API + "/__reset");
// ═══ 1) Menu: placas (abertura 3D), Menu com Reprodução aberta, depois Módulos aberto (item "Protocolos", fora de Reprodução) ═══
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
mapa.menuRepro = (await coletar()).menu;
await p.locator("button[aria-expanded]", { hasText: "Reprodução" }).first().click(); await esp(500);
await p.locator("button[aria-expanded]", { hasText: "Módulos" }).first().click(); await esp(700);
await p.evaluate(() => { const it = [...document.querySelectorAll("button")].find((x) => /^Protocolos\s/.test(x.innerText.trim()) && !/IATF/.test(x.innerText)); it.scrollIntoView({ block: "center" }); }); await esp(700);
await p.screenshot({ path: OUT + "menu_mod.png" }); mapa.menuMod = await coletar(); log("menuMod", JSON.stringify(mapa.menuMod.menu.map((i) => [i.txt.slice(0, 14), Math.round(i.y)])));
// ═══ 2) Protocolos › Em andamento ═══
await p.evaluate(() => [...document.querySelectorAll("button")].find((x) => /^Protocolos\s/.test(x.innerText.trim()) && !/IATF/.test(x.innerText)).click()); await esp(2400); await topo();
await p.screenshot({ path: OUT + "pl_vp.png" });
await alta("pl0");
// ═══ 3) Detalhe do protocolo IATF: um cartão por dia ═══
await p.locator(".mob-card", { hasText: "IATF 3 MANEJOS" }).first().click(); await esp(2400); await topo();
await p.screenshot({ path: OUT + "pd_vp.png" });
await alta("pd0");
// ═══ 4) Baixa do D7 (dia de hoje): data, animais, o que aplicar, frasco ═══
await p.locator(".mob-card", { hasText: "D7" }).first().click(); await esp(1200); await topo();
await p.screenshot({ path: OUT + "pb_vp.png" });
await alta("pb0");                                   // 5 de 5, frasco ainda não escolhido
await p.locator("label", { hasText: "3344" }).locator('input[type="checkbox"]').click(); await esp(500);
await alta("pb1");                                   // 3344 desmarcada → 4 de 5
const selFrasco = p.locator("select").first();
await selFrasco.evaluate((s) => { s.size = s.options.length; }); await esp(500);
await alta("pb_fr");                                 // lista de frascos aberta (select nativo não abre no headless: <select size>)
await selFrasco.evaluate((s) => { s.removeAttribute("size"); s.size = 0; });
await selFrasco.selectOption({ index: 1 }); await esp(600);
await alta("pb2");                                   // frasco escolhido (Prostaglandina 50 ml)
// ═══ 5) Confirmar baixa → de volta aos cartões, com o aviso de estoque da resposta ═══
await p.getByRole("button", { name: "Confirmar baixa" }).click(); await esp(2200); await topo();
await p.screenshot({ path: OUT + "pd1_vp.png" });
await alta("pd1");
mapa.log3 = await (await fetch(API + "/__log3")).json();
// ═══ 6) Protocolo SANITÁRIO: frasco + lote (a escolha de lote só existe aqui, igual ao backend) ═══
await p.getByRole("button", { name: "Voltar" }).first().click(); await esp(1500); await topo();
await p.locator(".mob-card", { hasText: "VERMIFUGAÇÃO" }).first().click(); await esp(2200); await topo();
await alta("ps0");
await p.locator(".mob-card", { hasText: "D9" }).first().click(); await esp(1200); await topo();
await alta("ps1");
const selS = p.locator("select").first();
await selS.selectOption({ index: 1 }); await esp(700);
await alta("ps2");                                   // frasco com 2 lotes → aparece "De qual lote?" (Automático — mais antigo primeiro)
const selL = p.locator("select").nth(1);
await selL.evaluate((s) => { s.size = s.options.length; }); await esp(500);
await alta("ps_lote");                               // lista de lotes aberta
fs.writeFileSync(OUT + "mapa.json", JSON.stringify(mapa, null, 1));
await br.close(); log("ok");
