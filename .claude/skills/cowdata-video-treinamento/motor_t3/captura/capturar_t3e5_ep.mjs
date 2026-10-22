// T3 · Ep. 5 (Alimentação: Plano por lote e Consultar dietas — Menu › Alimentação) — telas REAIS do app em produção contra o stub (EP=t3e5), DPR 3 por padrão.
// Saída em shots_ep/: placas do Menu (recolhidas e Alimentação aberta), Menu com Alimentação aberta (itens Plano por Lote / Lançar nova dieta / Consultar dietas),
// e as telas REAIS como PÁGINAS ALTAS (cabeçalho e barra escondidos; o motor rola a imagem por trás das barras reais): Plano por Lote (pl0), Lançar nova dieta com o
// editor "Tratos por dia" em 3 tratos 40/30/30 (ld0), Consultar dietas (cs0) e a mesma lista com a dieta encerrada do 01 - Alta aberta (cs1) + mapa.json com as caixas
// reais do DOM (px CSS; páginas altas em coordenadas do documento).
//   EP=t3e5 STUB_PORT=8500 node stub-api.mjs &   ·   next start -p 3500   →   STUB=8500 APP=3500 node capturar_t3e5_ep.mjs      DSF=1 para teste rápido
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
  try { for (const k of Object.keys(localStorage)) if (k.startsWith("rascunho") || k.startsWith("mob_cache") || k.startsWith("menu_ciclos") || k.startsWith("menu_plano") || k.startsWith("menu_consultar") || k.startsWith("menu_lancar")) localStorage.removeItem(k); } catch {}
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
  // caixa de um trecho de texto dentro de um elemento, mesmo quando o React separa o texto em vários nós ("{n} animais · {k} tratos (…)")
  const trecho = (el, re) => { if (!el) return null; const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT), ns = []; let n, all = ""; while ((n = w.nextNode())) { ns.push([n, all.length]); all += n.textContent; }
    const m = all.match(re); if (!m) return null; const i0 = m.index, i1 = m.index + m[0].length; const rg = document.createRange(); let ok0 = false, ok1 = false;
    for (const [nd, off] of ns) { const L = nd.textContent.length; if (!ok0 && i0 < off + L) { rg.setStart(nd, i0 - off); ok0 = true; } if (!ok1 && i1 <= off + L) { rg.setEnd(nd, i1 - off); ok1 = true; break; } }
    return ok0 && ok1 ? box(rg.getBoundingClientRect()) : null; };
  const o = { docH: Math.max(document.documentElement.scrollHeight, document.body.scrollHeight) };
  const hdr = document.querySelector("header"), nav = document.querySelector("nav.mob-nav");
  o.hdrBottom = hdr ? hdr.getBoundingClientRect().bottom : 0; o.navTop = nav ? nav.getBoundingClientRect().top : 844;
  o.voltar = R(document.querySelector('button[aria-label="Voltar"]')); o.titulo = R(document.querySelector("h1")); o.tituloTxt = txt(document.querySelector("h1"));
  const folhas = (c) => [...c.querySelectorAll("*")].filter((e) => e.children.length === 0 && txt(e)).map((e) => ({ txt: txt(e), ...R(e), cor: getComputedStyle(e).color, fs: getComputedStyle(e).fontSize }));
  // cartões (Plano por Lote, Consultar dietas): caixa, folhas de texto, linhas filhas diretas, trechos do cabeçalho do Plano
  o.cards = [...document.querySelectorAll(".mob-card")].map((c) => ({ txt: txt(c), ...R(c), folhas: folhas(c), linhas: [...c.children].map((d) => ({ txt: txt(d), ...R(d) })),
    efetivo: trecho(c, /\d+ animais?/), tratos: trecho(c, /\d tratos? \([^)]*\)/), cab: trecho(c, /[\d.,]+ \w+\/cab/), dia: trecho(c, /[\d.,]+ \w+\/dia/), tratosN: trecho(c, /\d tratos?(?= \()/), tratosPct: trecho(c, /\([^)]*\)/) }));
  o.ps = [...document.querySelectorAll("p")].map((e) => ({ txt: txt(e), ...R(e), cor: getComputedStyle(e).color }));
  o.menuItens = [...document.querySelectorAll("button")].filter((b) => /^(Plano por Lote|Lançar nova dieta|Consultar dietas|Necessidade Mensal)/.test(txt(b))).map((b) => ({ txt: txt(b), ...R(b) }));
  o.heads = [...document.querySelectorAll("button[aria-expanded]")].map((b) => ({ txt: txt(b), aberta: b.getAttribute("aria-expanded"), ...R(b), pai: R(b.parentElement) }));
  // Lançar nova dieta: editor "Tratos por dia" (EditorTratosDieta)
  const rot = [...document.querySelectorAll("span")].find((e) => txt(e) === "Tratos por dia");
  if (rot) { const ed = rot.parentElement;
    o.editor = { caixa: R(ed), titulo: R(rot),
      pills: [...ed.querySelectorAll("button")].slice(0, 4).map((b) => ({ txt: txt(b), ...R(b) })),
      pillsUniao: (() => { const bs = [...ed.querySelectorAll("button")].slice(0, 4).map((b) => b.getBoundingClientRect()); const x0 = Math.min(...bs.map((r) => r.x)), y0 = Math.min(...bs.map((r) => r.y)), x1 = Math.max(...bs.map((r) => r.right)), y1 = Math.max(...bs.map((r) => r.bottom)); return box({ x: x0, y: y0, width: x1 - x0, height: y1 - y0 }); })(),
      rotuloPct: R([...ed.querySelectorAll("span")].find((e) => /^% de cada trato/.test(txt(e)))),
      labels: [...ed.querySelectorAll("label")].map((l) => ({ txt: txt(l), ...R(l), span: R(l.querySelector("span")), input: R(l.querySelector("input")), valor: l.querySelector("input")?.value ?? null })),
      soma: R([...ed.querySelectorAll("p")].find((e) => /^Soma:|^Os %/.test(txt(e)))), somaTxt: txt([...ed.querySelectorAll("p")].find((e) => /^Soma:|^Os %/.test(txt(e)))),
      rotuloSobra: R([...ed.querySelectorAll("span")].find((e) => /^A sobra do cocho/.test(txt(e)))),
      pillsSobra: [...ed.querySelectorAll("button")].slice(4).map((b) => ({ txt: txt(b), ativa: b.getAttribute("aria-pressed") === "true", ...R(b) })),
      explica: R([...ed.querySelectorAll("p")].find((e) => /^Define o ciclo/.test(txt(e)))), explicaTxt: txt([...ed.querySelectorAll("p")].find((e) => /^Define o ciclo/.test(txt(e)))) };
    const bs2 = [...ed.querySelectorAll("button")].slice(4).map((b) => b.getBoundingClientRect());
    if (bs2.length) { const x0 = Math.min(...bs2.map((r) => r.x)), y0 = Math.min(...bs2.map((r) => r.y)), x1 = Math.max(...bs2.map((r) => r.right)), y1 = Math.max(...bs2.map((r) => r.bottom)); o.editor.pillsSobraUniao = box({ x: x0, y: y0, width: x1 - x0, height: y1 - y0 }); }
    o.campos = [...document.querySelectorAll("label")].filter((l) => !ed.contains(l)).map((l) => ({ txt: txt(l), ...R(l) }));
  }
  // Consultar dietas expandida: cabeçalho (nome · animais · tratos), itens (nome + linha T/dia/cab) e Vagão
  const cabec = [...document.querySelectorAll("div")].find((e) => e.children.length === 0 && / animais? · \d tratos?/.test(txt(e)));
  if (cabec) { o.apres = { cab: R(cabec), cabTxt: txt(cabec), tratosTrecho: trecho(cabec, /\d tratos? \([^)]*\)/), animaisTrecho: trecho(cabec, /\d+ animais?/), tratosN: trecho(cabec, /\d tratos?(?= \()/), tratosPct: trecho(cabec, /\([^)]*\)/) };
    const aberto = cabec.parentElement; const itens = [...aberto.children].filter((d) => d.children.length === 2 && d.children[1]?.children.length === 3);
    o.apres.itens = itens.map((d) => ({ txt: txt(d), ...R(d), nome: R(d.children[0]), linha: R(d.children[1]), t: R(d.children[1].children[0]), tTxt: txt(d.children[1].children[0]), dia: R(d.children[1].children[1]), cab: R(d.children[1].children[2]) }));
    const vag = [...aberto.children].find((d) => /^Vagão:/.test(txt(d))); o.apres.vagao = R(vag); o.apres.vagaoTxt = txt(vag); o.apres.vagaoT = R(vag?.querySelector("span")); o.apres.vagaoDia = vag ? trecho(vag, /[\d.,]+ kg\/dia/) : null;
    o.apres.bloco = R(aberto); }
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
const abrirItem = async (re) => { await p.evaluate((s) => [...document.querySelectorAll("button")].find((x) => new RegExp(s).test(x.innerText.trim())).click(), re); };
const voltar = async () => { await p.getByRole("button", { name: "Voltar" }).first().click(); await esp(1300); await topo(); };

await fetch(API + "/__reset");
// ═══ 1) Menu: placas recolhidas (abertura 3D) e Menu com Alimentação aberta ═══
const COLAPSADAS = ["protocolos-restrito", "reproducao", "sanidade", "alimentacao", "producao", "gestao", "financeiro", "modulos", "administracao", "app"];
await p.goto(APP + "/app/menu", { waitUntil: "networkidle" }); await esp(1500);
await p.evaluate((c) => localStorage.setItem("mob_menu_secoes_colapsadas", JSON.stringify(c)), COLAPSADAS);
await p.reload({ waitUntil: "networkidle" }); await esp(1500);
const heads = await p.$$eval("button[aria-expanded]", (bs) => bs.map((b) => { const rr = (b.parentElement || b).getBoundingClientRect(); return { txt: b.innerText.replace(/\s+/g, " ").trim(), px: rr.x, py: rr.y, pw: rr.width, ph: rr.height }; }));
const nomes = ["reproducao", "sanidade", "alimentacao", "producao", "gestao", "financeiro"];
for (let i = 0; i < 6; i++) { const h = heads[i]; await p.screenshot({ path: OUT + `placa_${nomes[i]}.png`, clip: { x: h.px, y: h.py, width: h.pw, height: h.ph } }); }
mapa.heads = heads; mapa.placasNomes = nomes;
await p.locator("button[aria-expanded]", { hasText: "Alimentação" }).first().click(); await esp(900);
await p.screenshot({ path: OUT + "menu_alim.png" });
{ const r = await p.locator("button[aria-expanded]", { hasText: "Alimentação" }).first().evaluate((b) => { const r = b.parentElement.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; }); await p.screenshot({ path: OUT + "placa_alimentacao_aberta.png", clip: { x: r.x, y: r.y, width: r.w, height: r.h } }); mapa.alimCard = r; }
mapa.menu_alim = await coletar(); log("menu_alim", JSON.stringify(mapa.menu_alim.menuItens.map((i) => [i.txt.slice(0, 22), Math.round(i.y)])), JSON.stringify(mapa.menu_alim.heads.map((h) => [h.txt.slice(0, 12), h.aberta, Math.round(h.pai.y), Math.round(h.pai.h)])));
// ═══ 2) Plano por Lote ═══
await abrirItem("^Plano por Lote"); await p.waitForSelector("text=Lote 1", { timeout: 15000 }); await esp(1800); await topo();
await p.screenshot({ path: OUT + "pl_vp.png" }); mapa.pl_vp = await coletar();
await alta("pl0");
// ═══ 3) Voltar → Menu (a seção segue aberta?) → Lançar nova dieta ═══
await voltar(); await p.screenshot({ path: OUT + "menu_alim_volta.png" }); mapa.menu_alim_volta = await coletar();
log("menu volta", JSON.stringify(mapa.menu_alim_volta.menuItens.map((i) => [i.txt.slice(0, 22), Math.round(i.y)])));
if (!mapa.menu_alim_volta.menuItens.length) { await p.locator("button[aria-expanded]", { hasText: "Alimentação" }).first().click(); await esp(900); mapa.menu_alim_volta = await coletar(); log("reabri Alimentação"); }
await abrirItem("^Lançar nova dieta"); await p.waitForSelector("text=Tratos por dia", { timeout: 15000 }); await esp(1500); await topo();
await p.selectOption("select.mob-input >> nth=0", "01"); await esp(1500);
await p.getByRole("button", { name: "3", exact: true }).first().click(); await esp(400);
{ const ins = p.locator('input[type=number]'); // Trato 1, 2, 3 (os campos de data são type=date)
  await ins.nth(0).fill("40"); await ins.nth(1).fill("30"); await ins.nth(2).fill("30"); await esp(500); }
await topo(); await p.screenshot({ path: OUT + "ld_vp.png" }); mapa.ld_vp = await coletar();
await alta("ld0");
// ═══ 4) Voltar → Consultar dietas (lista) → abre a dieta encerrada do 01 - Alta ═══
await voltar();
if (!(await coletar()).menuItens.length) { await p.locator("button[aria-expanded]", { hasText: "Alimentação" }).first().click(); await esp(900); }
await abrirItem("^Consultar dietas"); await p.waitForSelector("text=Encerrada", { timeout: 15000 }); await esp(1500); await topo();
await p.screenshot({ path: OUT + "cs_vp.png" }); mapa.cs_vp = await coletar();
await alta("cs0");
await p.locator(".mob-card", { hasText: "Encerrada" }).filter({ hasText: "Lote 1" }).first().locator("button").first().click(); await p.waitForSelector("text=Vagão", { timeout: 15000 }); await esp(1500); await topo();
await alta("cs1");
// ═══ 5) Plano de novo, para o 05 - Pré-parto (mesma captura pl0) e Menu → fecha ═══
fs.writeFileSync(OUT + "mapa.json", JSON.stringify(mapa, null, 1));
await br.close(); log("ok");
