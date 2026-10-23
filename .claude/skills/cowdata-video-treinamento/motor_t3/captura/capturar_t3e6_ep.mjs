// T3 · Ep. 6 (Produção — Menu › Produção, módulo inteiro) — telas REAIS do app em produção contra o stub (EP=t3e6), DPR 3 por padrão.
// Saída em shots_ep/: placas do Menu (recolhidas e Produção aberta), Menu com Produção aberta (os 5 itens) e as telas REAIS como PÁGINAS ALTAS (cabeçalho e barra escondidos;
// o motor rola a imagem por trás das barras reais; páginas longas são cortadas em 5200 px): Últimos controles (uc0 padrão · uc1 "Lote(s)" sem lote marcado · uc1b só o 01 · uc2 01 e 02),
// Qualidade do leite (ql0 tanque · ql1 individual), Secagens (se0), BST (bs0), Pesagens (pe0) + mapa.json com as caixas reais do DOM (px CSS; páginas altas em coordenadas do documento).
//   EP=t3e6 STUB_PORT=8600 node stub-api.mjs &   ·   next start -p 3600   →   STUB=8600 APP=3600 node capturar_t3e6_ep.mjs      DSF=1 para teste rápido
// O app em produção foi compilado com a API em localhost:8000: as chamadas são redirecionadas para a porta do stub por context.route. Hoje = 23/10/2026 (relógio fixo).
import fs from "fs";
import { chromium, novoContexto, pagina } from "./lib.mjs";
const DSF = Number(process.env.DSF || 3), OUT = "shots_ep/"; fs.mkdirSync(OUT, { recursive: true });
const STUB = process.env.STUB || 8000, APPP = process.env.APP || 3000, API = `http://localhost:${STUB}`, APP = `http://localhost:${APPP}`;
const ALTURA_MAX = 5200;
const br = await chromium.launch({ args: ["--lang=pt-BR"], env: { ...process.env, LANGUAGE: "pt_BR", LC_ALL: "pt_BR.UTF-8", LANG: "pt_BR.UTF-8" } });
const ctx = await novoContexto(br, 844, DSF);
await ctx.addInitScript(() => {
  localStorage.setItem("usuario", JSON.stringify({ id: 1, nome: "Bernadete", papel: "admin", eh_dono: true, permissoes: [] }));
  // o cabeçalho do app traz o nome REAL da fazenda (fixo em app/app/layout.tsx): troca em memória pelo nome fictício; nenhum nome real vai ao quadro
  const trocar = () => { for (const p of document.querySelectorAll("header p")) if (p.textContent.includes("Estreito Ponte de Pedra")) p.textContent = "Fazenda Boa Esperança"; };
  new MutationObserver(trocar).observe(document, { childList: true, subtree: true, characterData: true }); document.addEventListener("DOMContentLoaded", trocar);
  try { for (const k of Object.keys(localStorage)) if (k.startsWith("rascunho") || k.startsWith("mob_cache") || k.startsWith("menu_")) localStorage.removeItem(k); } catch {}
});
if (STUB != 8000) await ctx.route("http://localhost:8000/**", (r) => r.continue({ url: r.request().url().replace("localhost:8000", "localhost:" + STUB) }));
const p = await pagina(ctx); await p.clock.setFixedTime(new Date("2026-10-23T10:05:00-03:00")); const esp = (ms = 700) => p.waitForTimeout(ms);
const mapa = { dsf: DSF }; const log = (...a) => console.log(...a);
const topo = async () => { await p.evaluate(() => { document.activeElement?.blur?.(); window.scrollTo(0, 0); document.body.scrollTo(0, 0); document.scrollingElement.scrollTo(0, 0); }); await esp(350); };

// ── caixas reais (px CSS, coordenadas do documento) ──
const coletar = () => p.evaluate((ALT) => {
  const sy = window.scrollY, box = (r) => ({ x: +r.x.toFixed(2), y: +(r.y + sy).toFixed(2), w: +r.width.toFixed(2), h: +r.height.toFixed(2) });
  const R = (e) => (e ? box(e.getBoundingClientRect()) : null);
  const txt = (e) => (e?.innerText || "").replace(/\s+/g, " ").trim();
  const tight = (e) => { if (!e) return null; const rg = document.createRange(); rg.selectNodeContents(e); return box(rg.getBoundingClientRect()); }; // caixa justa do texto do elemento
  const uniao = (...els) => { const bs = els.filter(Boolean).map((e) => e.getBoundingClientRect()); if (!bs.length) return null; const x0 = Math.min(...bs.map((r) => r.x)), y0 = Math.min(...bs.map((r) => r.y)), x1 = Math.max(...bs.map((r) => r.right)), y1 = Math.max(...bs.map((r) => r.bottom)); return box({ x: x0, y: y0, width: x1 - x0, height: y1 - y0 }); };
  // caixa de um trecho de texto dentro de um elemento, mesmo quando o React separa o texto em vários nós
  const trecho = (el, re) => { if (!el) return null; const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT), ns = []; let n, all = ""; while ((n = w.nextNode())) { ns.push([n, all.length]); all += n.textContent; }
    const m = all.match(re); if (!m) return null; const i0 = m.index, i1 = m.index + m[0].length; const rg = document.createRange(); let ok0 = false, ok1 = false;
    for (const [nd, off] of ns) { const L = nd.textContent.length; if (!ok0 && i0 < off + L) { rg.setStart(nd, i0 - off); ok0 = true; } if (!ok1 && i1 <= off + L) { rg.setEnd(nd, i1 - off); ok1 = true; break; } }
    return ok0 && ok1 ? box(rg.getBoundingClientRect()) : null; };
  const o = { docH: Math.min(ALT, Math.max(document.documentElement.scrollHeight, document.body.scrollHeight)), docHReal: Math.max(document.documentElement.scrollHeight, document.body.scrollHeight) };
  const hdr = document.querySelector("header"), nav = document.querySelector("nav.mob-nav");
  o.hdrBottom = hdr ? hdr.getBoundingClientRect().bottom : 0; o.navTop = nav ? nav.getBoundingClientRect().top : 844;
  o.voltar = R(document.querySelector('button[aria-label="Voltar"]')); o.titulo = R(document.querySelector("h1")); o.tituloTxt = txt(document.querySelector("h1")); o.tituloTight = tight(document.querySelector("h1"));
  // Menu: itens da seção Produção e cabeçalhos das seções
  o.menuItens = [...document.querySelectorAll("button")].filter((b) => /^(Últimos controles leiteiros|Qualidade do leite|Secagens|BST — aplicações|Pesagens)/.test(txt(b))).map((b) => ({ txt: txt(b), ...R(b), titulo: tight(b.querySelector("span,p,div")), kids: [...b.querySelectorAll("*")].filter((e) => e.children.length === 0 && txt(e)).map((e) => ({ txt: txt(e), ...R(e) })) }));
  o.heads = [...document.querySelectorAll("button[aria-expanded]")].map((b) => ({ txt: txt(b), aberta: b.getAttribute("aria-expanded"), ...R(b), pai: R(b.parentElement) }));
  // período (De / Até)
  const datas = [...document.querySelectorAll("input[type=date]")];
  if (datas.length >= 2) { const l0 = datas[0].closest("label"), l1 = datas[1].closest("label");
    o.periodo = { de: R(l0), ate: R(l1), uniao: uniao(l0, l1), inputDe: R(datas[0]), inputAte: R(datas[1]), rotDe: tight(l0.querySelector("span")), rotAte: tight(l1.querySelector("span")), deVal: datas[0].value, ateVal: datas[1].value }; }
  // escopo: Rebanho / Lote(s) / Animal(is)
  const g = document.querySelector('[role=group][aria-label=Escopo]');
  if (g) o.escopo = { caixa: R(g), btns: [...g.querySelectorAll("button")].map((b) => ({ txt: txt(b), ativa: b.getAttribute("aria-pressed") === "true", ...R(b), tight: tight(b) })) };
  o.lotePills = [...document.querySelectorAll("button.lote-pill")].map((b) => ({ txt: txt(b), ativa: b.getAttribute("aria-pressed") === "true", ...R(b) }));
  o.lotePillsUniao = uniao(...document.querySelectorAll("button.lote-pill"));
  o.nota = [...document.querySelectorAll("p.lote-nota")].map((e) => ({ txt: txt(e), ...R(e) }));
  // grupos de pílulas de opção exclusiva ("Controles por vaca", "Coleta", "Motivo", "Origem")
  o.grupos = [...document.querySelectorAll("div")].filter((d) => [...d.children].filter((c) => c.tagName === "BUTTON" && c.classList.contains("mob-pill")).length >= 2).map((d) => {
    const rot = d.previousElementSibling; const bs = [...d.children].filter((c) => c.tagName === "BUTTON");
    return { rotulo: txt(rot), rot: R(rot), rotTight: tight(rot), pills: bs.map((b) => ({ txt: txt(b), ativa: b.getAttribute("aria-pressed") === "true", ...R(b) })), uniao: R(d), comRotulo: uniao(rot, d) }; });
  // BST: campos "DEL na aplicação — de / até"
  o.delCampos = [...document.querySelectorAll("label")].filter((l) => l.querySelector("input[type=number]")).map((l) => ({ txt: txt(l), ...R(l), rot: tight(l.querySelector("span")), input: R(l.querySelector("input")) }));
  o.delUniao = o.delCampos.length ? uniao(...[...document.querySelectorAll("label")].filter((l) => l.querySelector("input[type=number]"))) : null;
  // exportar
  const bx = document.querySelector('button[title="Exportar para Excel"]'), bp = document.querySelector('button[title="Exportar para PDF"]');
  if (bx && bp) o.exportar = { excel: R(bx), pdf: R(bp), uniao: uniao(bx, bp) };
  // ordenação (Últimos controles e Pesagens)
  const sel = document.querySelector("select"); if (sel && !sel.classList.contains("mob-input")) o.ordenar = R(sel.parentElement);
  // cartões de registro (Nº …/Tanque) e resumo
  const todos = [...document.querySelectorAll(".mob-card")];
  const ehReg = (c) => /^(Nº|Tanque)/.test(txt(c.firstElementChild));
  o.resumo = todos.filter((c) => !ehReg(c) && !c.closest("section[aria-label^=Lote]")).map((c) => ({ txt: txt(c), ...R(c), kids: [...c.children].map((k) => ({ txt: txt(k), ...R(k), tight: tight(k) })) }))[0] ?? null;
  if (o.resumo) { const c = todos.find((x) => txt(x) === o.resumo.txt); o.resumo.vacasCtrl = trecho(c, /\d+ vacas? · \d+ controles?/); o.resumo.media = trecho(c, /Média [\d.,]+ kg/); o.resumo.n = trecho(c, /^\d+ \w+/); }
  o.regs = todos.filter(ehReg).slice(0, 14).map((c) => ({ txt: txt(c), ...R(c), kids: [...c.children].map((k) => ({ txt: txt(k), ...R(k), tight: tight(k) })),
    folhas: [...c.querySelectorAll("*")].filter((e) => e.children.length === 0 && txt(e)).map((e) => ({ txt: txt(e), ...R(e) })),
    tr: (() => { const fl = [...c.querySelectorAll("*")].filter((e) => e.children.length === 0 && txt(e)); // trechos medidos DENTRO de cada folha de texto (o texto do cartão inteiro junta nós sem espaço)
      const tl = (re, leaf) => { const e = fl.find((x) => leaf.test(txt(x))); return e ? trecho(e, re) : null; };
      return { lote: tl(/Lote .+$/, /Lote \d/), data: tl(/\d\d\/\d\d\/\d{4}/, /\d\d\/\d\d\/\d{4}/), delAp: tl(/DEL na aplicação \d+/, /DEL na aplicação/), delHoje: tl(/DEL hoje \d+/, /DEL hoje/),
        gmd: tl(/.+/, /kg\/dia$/), ultimo: tl(/→ .+$/, /→/), motivo: tl(/(Animal doente|Baixa produção|Comportamento|Mastite|Problema de casco|Rotina parto|Outros)/, /(Animal doente|Baixa produção|Comportamento|Mastite|Problema de casco|Rotina parto|Outros)/),
        sanidade: tl(/Sanidade/, /^Sanidade$/), kg: tl(/.+/, /^[\d.,]+ kg$/), del: tl(/.+/, /^DEL \d+$/),
        grade: (() => { const gd = [...c.querySelectorAll("div")].find((d) => d.children.length === 8); return gd ? [...gd.children].map((e) => ({ txt: txt(e), ...R(e) })) : null; })() }; })() }));
  o.nRegs = todos.filter(ehReg).length;
  o.blocos = [...document.querySelectorAll("section[aria-label^=Lote]")].map((s) => { const h = s.firstElementChild; return { rot: s.getAttribute("aria-label"), txt: txt(h), ...R(h), titulo: tight(h.children[0]), detalhe: tight(h.children[1]),
    vacas: trecho(h.children[1], /\d+ vacas?/), media: trecho(h.children[1], /média [\d.,]+ kg/), vacasMedia: trecho(h.children[1], /\d+ vacas? · média [\d.,]+ kg/) }; });
  // contagem "N coletas / N secagens / N animais" (parágrafo à esquerda do Excel/PDF)
  o.contagem = [...document.querySelectorAll("p")].filter((e) => /^\d+ (coletas?|secagens?|secagem|animais|animal|aplicações|aplicação)/.test(txt(e))).map((e) => ({ txt: txt(e), ...R(e), tight: tight(e) }))[0] ?? null;
  return o;
}, ALTURA_MAX);
// páginas altas: viewport = altura do documento (no máximo 5200 px), cabeçalho e barra escondidos (o motor rola a imagem por trás das barras reais)
async function alta(nome) {
  const estilo = await p.addStyleTag({ content: "header,nav.mob-nav{visibility:hidden!important}" });
  const H0 = await p.evaluate(() => Math.max(document.documentElement.scrollHeight, document.body.scrollHeight));
  await p.setViewportSize({ width: 390, height: Math.max(844, Math.min(H0, ALTURA_MAX)) }); await esp(1100); await topo();
  const m = await coletar(); await p.screenshot({ path: OUT + nome + ".png" });
  await p.setViewportSize({ width: 390, height: 844 }); await esp(500);
  await estilo.evaluate((e) => e.remove()); await topo();
  mapa[nome] = m; log("alta", nome, "docH", m.docH, "real", m.docHReal, "regs", m.nRegs);
}
const vp = async (nome) => { await p.screenshot({ path: OUT + nome + ".png" }); mapa[nome] = await coletar(); log("vp", nome); };
const abrirItem = async (re) => { await p.evaluate((s) => [...document.querySelectorAll("button")].find((x) => new RegExp(s).test(x.innerText.trim())).click(), re); };
const voltar = async () => { await p.getByRole("button", { name: "Voltar" }).first().click(); await esp(1300); await topo(); };
const aguardaLista = async (sel = "text=Nº", ms = 15000) => { await p.waitForSelector(sel, { timeout: ms }); await esp(1500); await topo(); };

await fetch(API + "/__reset");
// ═══ 1) Menu: placas recolhidas (abertura 3D) e Menu com Produção aberta ═══
const COLAPSADAS = ["protocolos-restrito", "reproducao", "sanidade", "alimentacao", "producao", "gestao", "financeiro", "modulos", "administracao", "app"];
await p.goto(APP + "/app/menu", { waitUntil: "networkidle" }); await esp(1500);
await p.evaluate((c) => localStorage.setItem("mob_menu_secoes_colapsadas", JSON.stringify(c)), COLAPSADAS);
await p.reload({ waitUntil: "networkidle" }); await esp(1500);
const heads = await p.$$eval("button[aria-expanded]", (bs) => bs.map((b) => { const rr = (b.parentElement || b).getBoundingClientRect(); return { txt: b.innerText.replace(/\s+/g, " ").trim(), px: rr.x, py: rr.y, pw: rr.width, ph: rr.height }; }));
const nomes = ["reproducao", "sanidade", "alimentacao", "producao", "gestao", "financeiro"];
for (let i = 0; i < 6; i++) { const h = heads[i]; await p.screenshot({ path: OUT + `placa_${nomes[i]}.png`, clip: { x: h.px, y: h.py, width: h.pw, height: h.ph } }); }
mapa.heads = heads; mapa.placasNomes = nomes;
await p.locator("button[aria-expanded]", { hasText: /^Produção/ }).first().click(); await esp(900);
await p.screenshot({ path: OUT + "menu_prod.png" }); // rolagem 0: é o Menu da abertura 3D (o corpo da página — BODY — é o contêiner de rolagem do app)
mapa.menu_prod = await coletar(); log("menu_prod", JSON.stringify(mapa.menu_prod.menuItens.map((i) => [i.txt.slice(0, 26), Math.round(i.y)])));
// a seção Produção aberta não cabe acima da barra: rola o Menu para fotografar o cartão inteiro (placa 3D) sem a barra por cima
await p.evaluate(() => document.body.scrollTo(0, 330)); await esp(500);
{ const r = await p.locator("button[aria-expanded]", { hasText: /^Produção/ }).first().evaluate((b) => { const r = b.parentElement.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; }); await p.screenshot({ path: OUT + "placa_producao_aberta.png", clip: { x: r.x, y: r.y, width: r.w, height: r.h } }); mapa.prodCard = r; log("placa aberta", JSON.stringify(r)); }
await topo();
await alta("mp0"); // o Menu como página alta: o motor rola a imagem por trás do cabeçalho e da barra reais
// ═══ 2) Últimos controles leiteiros ═══
await abrirItem("^Últimos controles leiteiros"); await aguardaLista();
await p.screenshot({ path: OUT + "uc_vp.png" }); mapa.uc_vp = await coletar();
await alta("uc0");
await p.getByRole("button", { name: "Lote(s)", exact: true }).click(); await esp(1500); await topo();
await alta("uc1");
await p.locator("button.lote-pill", { hasText: /^01 - Alta/ }).click(); await aguardaLista("section[aria-label^=Lote]");
await alta("uc1b");
await p.locator("button.lote-pill", { hasText: /^02 - Média/ }).click(); await esp(1500); await topo();
await alta("uc2");
// ═══ 3) Voltar → Menu (agora com o subtítulo "x kg no último") → Qualidade do leite ═══
await voltar(); if (!(await coletar()).menuItens.length) { await p.locator("button[aria-expanded]", { hasText: /^Produção/ }).first().click(); await esp(900); log("reabri Produção"); }
await alta("mp1"); // Menu depois de visitar os controles: o primeiro item ganha o subtítulo "x kg no último"
await abrirItem("^Qualidade do leite"); await aguardaLista("text=Tanque");
await alta("ql0");
await p.getByRole("button", { name: /^Individual/ }).click(); await aguardaLista();
await alta("ql1");
// ═══ 4) Secagens ═══
await voltar(); if (!(await coletar()).menuItens.length) { await p.locator("button[aria-expanded]", { hasText: /^Produção/ }).first().click(); await esp(900); }
await abrirItem("^Secagens"); await aguardaLista(); await alta("se0");
// ═══ 5) BST ═══
await voltar(); if (!(await coletar()).menuItens.length) { await p.locator("button[aria-expanded]", { hasText: /^Produção/ }).first().click(); await esp(900); }
await abrirItem("^BST"); await aguardaLista(); await alta("bs0");
// ═══ 6) Pesagens ═══
await voltar(); if (!(await coletar()).menuItens.length) { await p.locator("button[aria-expanded]", { hasText: /^Produção/ }).first().click(); await esp(900); }
await abrirItem("^Pesagens"); await aguardaLista(); await alta("pe0");
fs.writeFileSync(OUT + "mapa.json", JSON.stringify(mapa, null, 1));
await br.close(); log("ok");
