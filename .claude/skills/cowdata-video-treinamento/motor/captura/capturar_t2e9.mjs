// Temporada 2 · Ep. 9 — Sanidade › aplicação de medicamentos (Curativa › Aplicação de remédio e Preventiva › Aplicação). Captura as telas REAIS do app (produção) contra o stub (EP=t2e9).
// Rodar:  EP=t2e9 node stub-api.mjs &   (frontend: next start)   EP=t2e9 node capturar_t2e9.mjs      (DSF=escala opcional)
// O formulário é de UM animal / um lote, sem barra fixa de ação (barTop = topo da navegação). O seletor de produto é um modal estático (position:fixed), capturado em tela estática.
import fs from "fs";
import { chromium, novoContexto, pagina } from "./lib.mjs";
const OUT = "shots/"; fs.mkdirSync(OUT, { recursive: true }); const mapa = {};
const API = "http://localhost:8000";
const cfg = (o) => fetch(API + "/__cfg", { method: "POST", body: JSON.stringify(o) });
const br = await chromium.launch({ args: ["--lang=pt-BR"], env: { ...process.env, LANGUAGE: "pt_BR", LC_ALL: "pt_BR.UTF-8", LANG: "pt_BR.UTF-8" } });
const DSF = Number(process.env.DSF || 0) || undefined;

async function sessao() {
  await fetch(API + "/__reset");
  const ctx = await novoContexto(br, 844, DSF);
  // o cabeçalho do app tem o nome de uma fazenda real escrito direto no layout; no vídeo só vale o nome fictício
  await ctx.addInitScript(() => {
    const trocar = () => { for (const p of document.querySelectorAll("header p")) if (p.textContent.includes("Estreito Ponte de Pedra")) p.textContent = "Fazenda Boa Esperança"; };
    new MutationObserver(trocar).observe(document, { childList: true, subtree: true, characterData: true }); document.addEventListener("DOMContentLoaded", trocar);
    try { for (const k of Object.keys(localStorage)) if (k.startsWith("rascunho")) localStorage.removeItem(k); } catch {}
  });
  return { ctx, p: await pagina(ctx) };
}
let p;
const esp = (ms = 650) => p.waitForTimeout(ms);
async function caixas(sel) {
  const o = {};
  for (const [k, s] of Object.entries(sel)) {
    const l = p.locator(s).first();
    if (!(await l.count())) { o[k] = null; continue; }
    const b = await l.boundingBox(); o[k] = b && { x: +b.x.toFixed(1), y: +b.y.toFixed(1), w: +b.width.toFixed(1), h: +b.height.toFixed(1) };
  }
  return o;
}
const scrollar = (y) => p.evaluate((y) => { document.activeElement?.blur?.(); window.scrollTo(0, y); document.body.scrollTo(0, y); document.scrollingElement.scrollTo(0, y); }, y);
// tall = captura alta (viewport grande) para o motor rolar a imagem; scroll = posição da página na captura normal.
async function snap(nome, { tall = false, alvos = {}, scroll = 0, tallMax = 3000 } = {}) {
  await esp(); await scrollar(scroll); await esp(250);
  const navTop = await p.evaluate(() => document.querySelector("nav.mob-nav").getBoundingClientRect().top);
  await p.screenshot({ path: `${OUT}${nome}.png` });
  const m = { img: `${nome}.png`, w: 390, h: 844, hdr: 95.78, barTop: +navTop.toFixed(1), navTop: +navTop.toFixed(1), scroll, alvos: await caixas(alvos) };
  m.alvosN = m.alvos;
  if (tall) {
    // a lista de animais do seletor tem max-height 50vh: na captura alta ela cresceria; fixa em 50% de 844 px (o que o celular mostra)
    await p.addStyleTag({ content: '[style*="max-height: 50vh"]{max-height:422px !important}' });
    await p.setViewportSize({ width: 390, height: tallMax }); await esp(500);
    const fim = await p.evaluate((lim) => { let m = 0; document.querySelectorAll("main button.mob-btn, main p").forEach((e) => { const r = e.getBoundingClientRect(); if (r.height && r.bottom < lim - 50) m = Math.max(m, r.bottom); }); return m; }, tallMax); // fim do conteúdo = Salvar ou o aviso abaixo dele (a lista de animais rola por dentro e inflaria a medida)
    const H = Math.max(844, Math.ceil(fim + 24 + 69));
    await p.setViewportSize({ width: 390, height: H }); await esp(500);
    await scrollar(0); await esp(200);
    await p.screenshot({ path: `${OUT}${nome}_tall.png` });
    m.tall = { img: `${nome}_tall.png`, h: H, alvos: await caixas(alvos) };
    await p.setViewportSize({ width: 390, height: 844 }); await esp(500);
  }
  mapa[nome] = m; console.log(nome, tall ? `tall H=${m.tall.h}` : "", scroll ? `scroll=${scroll}` : "", "barTop", m.barTop);
}
const campo = (rot) => `div:has(> label:text-is("${rot}"))`;
const R = { animal: "Animal (nº / nome)", data: "Data", filtro: "Filtrar medicamento por", crit: "Doença", prod: "Produto / medicamento", qtd: "Quantidade (dose)", un: "Unidade", via: "Via de aplicação", resp: "Responsável", aplic: "Já foi aplicado?",
  evento: "Evento preventivo", dataRef: "Data de referência", rep: "Repetir a cada", med: "Medicamento aplicado", dose: "Dose", lote: "Lote" };
const ALV = {
  voltar1: 'button[aria-label="Voltar"] >> nth=0', voltar2: 'button[aria-label="Voltar"] >> nth=1',
  pillA: 'button.mob-pill:text-is("Animal")', pillL: 'button.mob-pill:text-is("Lote")', pills: 'button.mob-pill:text-is("Animal") >> xpath=..',
  animal: campo(R.animal), animalRot: campo(R.animal) + " > label", busca: 'input[placeholder="Buscar animal…"]', animalSel: campo(R.animal) + " > button",
  data: campo(R.data), dataIn: campo(R.data) + " input",
  filtro: campo(R.filtro), filtroSel: campo(R.filtro) + " select", crit: campo(R.crit), critSel: campo(R.crit) + " select",
  prod: campo(R.prod), prodBtn: campo(R.prod) + " button", prodRot: campo(R.prod) + " > label",
  banner: '.mob-card:has-text("substitutos indicados")', bannerTit: '.mob-card:has-text("substitutos indicados") > div >> nth=0', disp: 'div:text-is("Disponível agora")', usar: 'button:text-is("Usar")',
  comprar: 'div:text-is("Precisa comprar")', dispLinha: '.mob-card:has-text("substitutos indicados") div:has(> div > div:text-is("Cloxacilina"))',
  qtd: campo(R.qtd), qtdIn: campo(R.qtd) + " input", un: campo(R.un), unSel: campo(R.un) + " select", via: campo(R.via), viaSel: campo(R.via) + " select",
  resp: campo(R.resp), respSel: campo(R.resp) + " select", aplic: campo(R.aplic), aplicSim: 'button.mob-pill:has-text("Sim (aplicar agora)")',
  salvar: 'button.mob-btn:text-is("Salvar")', aviso: 'p:has-text("Lançamento salvo.")', rasc: 'p:has-text("Rascunho salvo")',
  // blocos das grades
  sanidade: "button.mob-bloco:has-text('Sanidade')", curativa: "button.mob-bloco:has-text('Curativa')", preventiva: "button.mob-bloco:has-text('Preventiva')",
  apl: "button.mob-bloco:has-text('Aplicação de remédio')", proto: "button.mob-bloco:has-text('Protocolo sanitário')",
  aplP: "button.mob-bloco:text-is('Aplicação')", calP: "button.mob-bloco:has-text('Calendário sanitário')", bstP: "button.mob-bloco:text-is('BST')",
  // preventiva
  evento: campo(R.evento), eventoSel: campo(R.evento) + " select", dataRef: campo(R.dataRef), rep: campo(R.rep), medP: campo(R.med), medBtn: campo(R.med) + " button", dose: campo(R.dose), doseIn: campo(R.dose) + " input",
  loteC: campo(R.lote), loteSel: campo(R.lote) + " select",
  // modal do seletor de produto (estático)
  modal: 'div[style*="position: fixed"] > .card', modTit: 'div[style*="position: fixed"] .card-header', modBusca: 'div[style*="position: fixed"] input', modTab: 'div[style*="position: fixed"] table', modTh: 'div[style*="position: fixed"] thead',
  rCef: 'div[style*="position: fixed"] tbody tr:has-text("Cefalexina")', rClo: 'div[style*="position: fixed"] tbody tr:has-text("Cloxacilina")', rCefti: 'div[style*="position: fixed"] tbody tr:has-text("Ceftiofur")',
  rFlu: 'div[style*="position: fixed"] tbody tr:has-text("Flunixina")', rCefEst: 'div[style*="position: fixed"] tbody tr:has-text("Cefalexina") td:nth-child(3)',
};
const irLancar = async () => { await p.goto("http://localhost:3000/app/lancar", { waitUntil: "networkidle" }); await esp(1400); };
const clicaBloco = async (sel) => { await p.locator(sel).first().click(); await esp(650); };
({ p } = await sessao());
await irLancar();
await snap("s01_lancar", { alvos: { san: ALV.sanidade, navLancar: "nav.mob-nav >> text=Lançar" } });
await clicaBloco(ALV.sanidade);
await snap("s02_grade", { alvos: { cur: ALV.curativa, prev: ALV.preventiva, v1: ALV.voltar1 } });
await clicaBloco(ALV.curativa);
await snap("s03_curativa", { alvos: { apl: ALV.apl, proto: ALV.proto, v1: ALV.voltar1, v2: ALV.voltar2 } });
await clicaBloco(ALV.apl); await esp(500);
await snap("s04_form", { alvos: { busca: ALV.busca, animal: ALV.animal, pillA: ALV.pillA, pillL: ALV.pillL } });
await p.fill(ALV.busca, "4318"); await esp(500);
await snap("s05_digitado", { alvos: { busca: ALV.busca, res: 'button.mob-btn-2:has-text("4318")', animal: ALV.animal } });
await p.locator('button.mob-btn-2', { hasText: "4318" }).first().click(); await esp(600);
await snap("s06_animal", { tall: true, alvos: ALV });
await p.selectOption(ALV.filtroSel, "doenca"); await esp(500);
await snap("s07_doenca", { tall: true, alvos: ALV });
await p.selectOption(ALV.critSel, "Mastite"); await esp(900);
await snap("s08_mastite", { tall: true, alvos: ALV });
await p.locator(ALV.prodBtn).first().click(); await esp(700);
await snap("s09_picker", { alvos: ALV, scroll: 160 });
await p.locator(ALV.rCef).click(); await esp(1200);
await snap("s10_baixo", { tall: true, alvos: ALV });
await p.locator(ALV.usar).first().click(); await esp(900);
await snap("s11_usar", { tall: true, alvos: ALV });
await p.fill(ALV.qtdIn, "1"); await esp(500);
await snap("s12_dose", { tall: true, alvos: ALV });
await p.selectOption(ALV.unSel, "unidade"); await esp(500);
await snap("s13_unidade", { tall: true, alvos: ALV });
await p.selectOption(ALV.viaSel, "Intramamária"); await esp(500);
await snap("s14_via", { tall: true, alvos: ALV });
await p.selectOption(ALV.respSel, "Adelino"); await esp(500);
await snap("s15_resp", { tall: true, alvos: ALV });
await cfg({ atraso: 700 });
await p.locator(ALV.salvar).scrollIntoViewIfNeeded(); await p.locator(ALV.salvar).click();
await p.waitForSelector(ALV.aviso, { timeout: 10000 }); await esp(900);
await snap("s16_salvo", { tall: true, alvos: ALV });
// volta: Aplicação de remédio → Curativa → grade (os dois toques em "Voltar" são filmados com as telas s03 e s02)
await p.locator(ALV.voltar2).click(); await esp(600);
await snap("s17_volta1", { alvos: { apl: ALV.apl, proto: ALV.proto, v1: ALV.voltar1, v2: ALV.voltar2 } });
await p.locator(ALV.voltar2).click(); await esp(600);
await snap("s18_volta2", { alvos: { cur: ALV.curativa, prev: ALV.preventiva, v1: ALV.voltar1 } });
// ───────────── Preventiva ─────────────
await clicaBloco(ALV.preventiva);
await snap("p01_grade", { alvos: { aplP: ALV.aplP, calP: ALV.calP, bstP: ALV.bstP, v1: ALV.voltar1, v2: ALV.voltar2 } });
await clicaBloco(ALV.aplP); await esp(500);
await snap("p02_form", { tall: true, alvos: ALV });
await p.selectOption(ALV.eventoSel, { label: "Vacina reprodutiva" }); await esp(800);
await snap("p03_evento", { tall: true, alvos: ALV });
await p.locator(ALV.pillL).click(); await esp(600);
await snap("p04_lote", { tall: true, alvos: ALV });
await p.selectOption(ALV.loteSel, "02 - Média"); await esp(500);
await snap("p05_lote02", { tall: true, alvos: ALV });
await p.locator(ALV.salvar).scrollIntoViewIfNeeded(); await p.locator(ALV.salvar).click();
await p.waitForSelector(ALV.aviso, { timeout: 10000 }); await esp(900);
await snap("p06_salvo", { tall: true, alvos: ALV });
const log = await (await fetch(API + "/__log")).json();
console.log("POSTs:", JSON.stringify(log.map((x) => [x.p, x.b])));
fs.writeFileSync("mapa.json", JSON.stringify(mapa, null, 1));
await br.close();
