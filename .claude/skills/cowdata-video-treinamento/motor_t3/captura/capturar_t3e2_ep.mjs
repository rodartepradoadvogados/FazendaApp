// T3 · Ep. 2 (Protocolos IATF em andamento) — telas REAIS do app em produção contra o stub (EP=t3e2), DPR 3 por padrão.
// Saída em shots_ep/: placas e Menu (abertura 3D), menu com "Módulos" aberto (relance do item Protocolos), páginas ALTAS da tela
// "Protocolos IATF" (normal e com o botão em "Gerando…"), a Folha de campo REAL (PDF baixado do app, rasterizado com pdftoppm) e mapa.json
// com as caixas reais do DOM (px CSS; páginas altas em coordenadas do documento) e as caixas do PDF (px da imagem, via pdftotext -bbox).
//   EP=t3e2 STUB_PORT=8100 node stub-api.mjs &   ·   next start -p 3100   →   STUB=8100 APP=3100 node capturar_t3e2_ep.mjs      DSF=1 para teste rápido
// O app em produção foi compilado com a API em localhost:8000: as chamadas são redirecionadas para a porta do stub por context.route.
import fs from "fs"; import { execSync } from "child_process";
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
// o PDF sai do código real do app; só o nome da fazenda (constante NOME_FAZENDA, real) é trocado pelo da fazenda fictícia
await ctx.route("**/_next/static/chunks/*.js", async (r) => { const resp = await r.fetch(); let b = await resp.text(); if (b.includes("Estreito Ponte de Pedra")) b = b.replaceAll("Fazenda Estreito Ponte de Pedra", "Fazenda Boa Esperança"); await r.fulfill({ response: resp, body: b }); });
const p = await pagina(ctx); const esp = (ms = 700) => p.waitForTimeout(ms);
const mapa = { dsf: DSF }; const log = (...a) => console.log(...a);
const topo = async () => { await p.evaluate(() => { document.activeElement?.blur?.(); window.scrollTo(0, 0); document.body.scrollTo(0, 0); document.scrollingElement.scrollTo(0, 0); }); await esp(350); };

// ── caixas reais (px CSS, coordenadas do documento) ──
const coletar = () => p.evaluate(() => {
  const sy = window.scrollY, R = (e) => { if (!e) return null; const r = e.getBoundingClientRect(); return { x: +r.x.toFixed(2), y: +(r.y + sy).toFixed(2), w: +r.width.toFixed(2), h: +r.height.toFixed(2) }; };
  const RR = (rg) => { const r = rg.getBoundingClientRect(); return { x: +r.x.toFixed(2), y: +(r.y + sy).toFixed(2), w: +r.width.toFixed(2), h: +r.height.toFixed(2) }; };
  const txt = (e) => (e?.innerText || "").replace(/\s+/g, " ").trim();
  const o = { docH: Math.max(document.documentElement.scrollHeight, document.body.scrollHeight) };
  const hdr = document.querySelector("header"), nav = document.querySelector("nav.mob-nav");
  o.hdrBottom = hdr ? hdr.getBoundingClientRect().bottom : 0; o.navTop = nav ? nav.getBoundingClientRect().top : 844;
  o.voltar = R(document.querySelector('button[aria-label="Voltar"]'));
  o.cards = [...document.querySelectorAll(".mob-card")].filter((c) => [...c.querySelectorAll("button")].some((b) => /Folha de campo/.test(b.textContent))).map((c) => {
    const kids = [...c.children]; const cab = kids[0], botao = kids[1], spans = [...cab.children];
    const d = { box: R(c), cab: R(cab), nome: R(spans[0]), nomeTxt: txt(spans[0]), d0: R(spans[1]), d0Txt: txt(spans[1]), botao: R(botao), botaoTxt: txt(botao), icone: R(botao.querySelector("svg")) };
    // texto do botão (sem o ícone) — caixa do nó de texto
    const tn = [...botao.childNodes].filter((n) => n.nodeType === 3 && n.textContent.trim()).pop(); if (tn) { const rg = document.createRange(); rg.selectNodeContents(tn); d.botaoTexto = RR(rg); }
    const resto = kids.slice(2);
    if (resto.length === 1 && /Concluído/.test(resto[0].innerText)) { // protocolo concluído
      const w = resto[0], [conc, prox, cand] = [...w.children];
      d.concluido = R(conc); d.concluidoTxt = txt(conc); d.proxima = R(prox); d.proximaData = R(prox.querySelector("span")); d.proximaTxt = txt(prox);
      if (cand) { const [tit, ...rows] = [...cand.children]; d.candTit = R(tit); d.candTitTxt = txt(tit);
        d.cands = rows.map((r) => { const [n, m] = [...r.children]; return { num: txt(n), motivo: txt(m), box: R(r), numBox: R(n), motivoBox: R(m) }; }); d.candLista = R(cand); }
    } else d.linhas = resto.map((r) => { // vacas em andamento
      const [esq, dir] = [...r.children], [n, selo] = [...esq.children], letra = dir.querySelector("span");
      const tn2 = [...dir.childNodes].filter((x) => x.nodeType === 3).pop(); let dataBox = null; if (tn2) { const rg = document.createRange(); rg.selectNodeContents(tn2); dataBox = RR(rg); }
      return { num: txt(n), box: R(r), numBox: R(n), selo: R(selo), seloTxt: txt(selo), seloCor: getComputedStyle(selo).color, seloFont: getComputedStyle(selo).fontSize, etapa: R(dir), etapaTxt: txt(dir), letra: R(letra), data: dataBox };
    });
    return d;
  });
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
const vp = async (nome, extra = {}) => { await p.screenshot({ path: OUT + nome + ".png" }); mapa[nome] = { ...(await coletar()), ...extra }; log("vp", nome); };
const boxesMenu = () => p.evaluate(() => {
  const R = (e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; };
  const items = [...document.querySelectorAll("button")].filter((b) => /Agenda Reprodutiva|Protocolos IATF|Ciclos de 21 dias|^Protocolos\b|Portal|Estoque|Recria/.test(b.innerText.trim().split("\n")[0])).map((b) => ({ txt: b.innerText.replace(/\s+/g, " ").trim(), ...R(b) }));
  const hdr = document.querySelector("header"), nav = document.querySelector("nav.mob-nav");
  return { items, hdrBottom: hdr.getBoundingClientRect().bottom, navTop: nav.getBoundingClientRect().top };
});

await fetch(API + "/__reset"); await fetch(API + "/__cfg2", { method: "POST", body: JSON.stringify({ atrasoDetalhe: 0 }) });
// ═══ 1) Menu: placas (abertura 3D) e Menu com Reprodução aberta ═══
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
mapa.menu = await boxesMenu(); log("menu", JSON.stringify(mapa.menu.items.map((i) => i.txt)));
// ═══ 1b) Menu com "Módulos" aberto: onde fica a baixa (item "Protocolos", fora de Reprodução) ═══
await p.locator("button[aria-expanded]", { hasText: "Reprodução" }).first().click(); await esp(500);
await p.locator("button[aria-expanded]", { hasText: "Módulos" }).first().click(); await esp(700);
await p.evaluate(() => { const it = [...document.querySelectorAll("button")].find((x) => /^Protocolos\s/.test(x.innerText.trim()) && !/IATF/.test(x.innerText)); it.scrollIntoView({ block: "center" }); }); await esp(700);
await p.screenshot({ path: OUT + "menu_mod.png" }); mapa.menuMod = await boxesMenu(); log("menuMod", JSON.stringify(mapa.menuMod.items.map((i) => [i.txt.slice(0, 12), Math.round(i.y)])));
// volta ao Menu com Reprodução aberta e entra em Protocolos IATF
await p.locator("button[aria-expanded]", { hasText: "Módulos" }).first().click(); await esp(400);
await p.locator("button[aria-expanded]", { hasText: "Reprodução" }).first().click(); await esp(600); await topo();
// ═══ 2) Protocolos IATF ═══
await p.locator("button", { hasText: "Protocolos IATF" }).first().click(); await esp(2400); await topo();
await p.screenshot({ path: OUT + "pi_vp.png" });
await alta("pi0");
// ═══ 3) Folha de campo (PDF): "Gerando…" (a Central demora para responder) → download real do jsPDF ═══
await fetch(API + "/__cfg2", { method: "POST", body: JSON.stringify({ atrasoDetalhe: 7000 }) });
const dl = p.waitForEvent("download", { timeout: 60000 });
await p.locator("button", { hasText: "Folha de campo" }).first().click(); await esp(600);
await alta("pi_ger");
const d = await dl; await d.saveAs(OUT + "folha.pdf"); log("pdf", d.suggestedFilename());
await esp(800); await fetch(API + "/__cfg2", { method: "POST", body: JSON.stringify({ atrasoDetalhe: 0 }) });
await topo();
// ═══ 4) PDF → imagem (pdftoppm) + caixas das palavras (pdftotext -bbox) ═══
const DPI = 220; execSync(`pdftoppm -r ${DPI} -png -f 1 -l 1 ${OUT}folha.pdf ${OUT}folha_pg`); 
const pgs = fs.readdirSync(OUT).filter((f) => /^folha_pg.*\.png$/.test(f)); fs.renameSync(OUT + pgs[0], OUT + "folha_pdf.png");
execSync(`pdftotext -bbox -f 1 -l 1 ${OUT}folha.pdf ${OUT}folha_bbox.html`);
const html = fs.readFileSync(OUT + "folha_bbox.html", "utf8"); const k = DPI / 72;
const pg = html.match(/<page width="([\d.]+)" height="([\d.]+)"/); const palavras = [...html.matchAll(/<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)<\/word>/g)].map((m) => ({ x: +m[1] * k, y: +m[2] * k, w: (+m[3] - +m[1]) * k, h: (+m[4] - +m[2]) * k, t: m[5].replace(/&amp;/g, "&").replace(/&#39;/g, "'") }));
mapa.pdf = { dpi: DPI, w: Math.round(+pg[1] * k), h: Math.round(+pg[2] * k), palavras };
fs.writeFileSync(OUT + "mapa.json", JSON.stringify(mapa, null, 1)); fs.unlinkSync(OUT + "folha_bbox.html");
await br.close(); log("ok");
