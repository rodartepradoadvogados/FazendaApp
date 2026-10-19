// Temporada 2 · Ep. 11 — Alimentação › consumo e sobra de cocho (Lançar › Outros lançamentos frequentes › Alimentação = FormAlimentacao). Captura as telas REAIS do app (produção) contra o stub (EP=t2e11).
// Rodar:  EP=t2e11 node stub-api.mjs &   (frontend: next start)   EP=t2e11 node capturar_t2e11.mjs      (DSF=escala opcional)
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
const linha = (nome) => `xpath=//div[div/div[text()="${nome}"]]`;
const ALV = {
  voltar1: 'button[aria-label="Voltar"] >> nth=0',
  alimentacao: "button.mob-bloco:has-text('Alimentação')", outros: ".mob-secao:text-is('Outros lançamentos frequentes')",
  lote: campo("Lote"), loteSel: campo("Lote") + " select", data: campo("Data"), dataIn: campo("Data") + " input",
  jaSec: ".mob-secao:text-is('Já lançado hoje')", jaCard: ".mob-secao:text-is('Já lançado hoje') + .mob-card", jaTotal: "span:text-is('Total fornecido')", jaTotalLinha: "div:has(> span:text-is('Total fornecido'))",
  sobraHoje: "div:text-matches('^Sobra de hoje')", nada: "span:text-is('Nada lançado ainda hoje.')",
  consSec: ".mob-secao:text-is('Lançar consumo')", consCard: ".mob-secao:text-is('Lançar consumo') + .mob-card",
  como: campo("Como informar a quantidade?"), modoAn: 'button:text-is("Nº de animais")', modoKg: 'button:text-is("Kg direto")', modos: 'button:text-is("Nº de animais") >> xpath=..',
  numAn: campo("Número de animais"), numIn: campo("Número de animais") + " input",
  silagem: linha("Silagem de milho"), concentrado: linha("Concentrado lactação"), feno: linha("Feno de tifton"), nucleo: linha("Núcleo mineral"),
  silIn: linha("Silagem de milho") + "/input", conIn: linha("Concentrado lactação") + "/input",
  silVal: linha("Silagem de milho") + "/strong",
  lancarCons: 'button.mob-btn:text-is("Lançar consumo")', avisoCons: 'p:has-text("Consumo lançado.")',
  sobraSec: ".mob-secao:text-is('Sobra do cocho')", sobraCard: ".mob-secao:text-is('Sobra do cocho') + .mob-card", sobra: campo("Sobra (kg totais)"), sobraIn: campo("Sobra (kg totais)") + " input",
  nota: 'p:has-text("Relançar hoje substitui")', lancarSobra: 'button.mob-btn:text-is("Lançar sobra")', avisoSobra: 'p:has-text("Lançamento salvo.")', rasc: 'p:has-text("Rascunho salvo")',
};
await sessao0();
async function sessao0() { ({ p } = await sessao()); }
await p.goto("http://localhost:3000/app/lancar", { waitUntil: "networkidle" }); await esp(1400);
await snap("a01_lancar", { alvos: { alimentacao: ALV.alimentacao, outros: ALV.outros } });
await p.locator(ALV.alimentacao).first().click(); await esp(900);
await snap("a02_form", { alvos: { lote: ALV.lote, loteSel: ALV.loteSel, data: ALV.data, v1: ALV.voltar1 } });
await p.selectOption(ALV.loteSel, { label: "01 - Alta" }); await esp(1200);
await snap("a03_lote", { tall: true, alvos: ALV });
await p.fill(ALV.numIn, "40"); await esp(700);
await snap("a04_num", { tall: true, alvos: ALV });
await p.locator(ALV.modoKg).first().click(); await esp(700);
await snap("a05_kg", { tall: true, alvos: ALV });
await p.fill(ALV.silIn, "1380"); await esp(600);
await snap("a06_kg1380", { tall: true, alvos: ALV });
await p.locator(ALV.modoAn).first().click(); await esp(700);
await snap("a07_volta", { tall: true, alvos: ALV });
await cfg({ atraso: 600 });
await p.locator(ALV.lancarCons).scrollIntoViewIfNeeded(); await p.locator(ALV.lancarCons).click();
await p.waitForSelector(ALV.avisoCons, { timeout: 10000 }); await esp(900);
await snap("a08_consumo", { tall: true, alvos: ALV });
await p.fill(ALV.sobraIn, "52"); await esp(700);
await snap("a09_sobra", { tall: true, alvos: ALV });
await p.locator(ALV.lancarSobra).scrollIntoViewIfNeeded(); await p.locator(ALV.lancarSobra).click();
await p.waitForSelector(ALV.avisoSobra, { timeout: 10000 }); await esp(900);
await snap("a10_sobra_ok", { tall: true, alvos: ALV });
const log = await (await fetch(API + "/__log")).json();
console.log("POSTs:", JSON.stringify(log.map((x) => [x.p, x.b])));
fs.writeFileSync("mapa.json", JSON.stringify(mapa, null, 1));
await br.close();
