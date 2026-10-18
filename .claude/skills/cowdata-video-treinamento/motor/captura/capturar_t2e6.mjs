// Temporada 2 · Ep. 6 — Produção › Controle leiteiro (por vaca e por lote). Captura as telas REAIS do app (produção) contra o stub (EP=t2e6).
// Rodar:  EP=t2e6 node stub-api.mjs &   (frontend: next start)   EP=t2e6 node capturar_t2e6.mjs
import fs from "fs";
import { chromium, novoContexto, pagina } from "./lib.mjs";
const OUT = "shots/"; fs.mkdirSync(OUT, { recursive: true }); const mapa = {};
const API = "http://localhost:8000";
const cfg = (o) => fetch(API + "/__cfg", { method: "POST", body: JSON.stringify(o) });
const br = await chromium.launch({ args: ["--lang=pt-BR"], env: { ...process.env, LANGUAGE: "pt_BR", LC_ALL: "pt_BR.UTF-8", LANG: "pt_BR.UTF-8" } });
const DSF_LOTE = Number(process.env.DSF_LOTE || 0); // a página do lote (40 cartões) passa de 16000 px na escala cheia: reduz a escala só dessa captura

async function sessao(dsf) {
  await fetch(API + "/__reset");
  const ctx = await novoContexto(br, 844, dsf);
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
const maxScroll = () => p.evaluate(() => Math.max(document.scrollingElement.scrollHeight - innerHeight, document.body.scrollHeight - innerHeight));
// O Controle leiteiro não tem barra fixa de ação (o Salvar fica no fim do formulário): barTop = topo da navegação.
// tall = captura alta (viewport grande) para o motor rolar a imagem; scroll = posição da página na captura normal
async function snap(nome, { tall = false, alvos = {}, scroll = 0, tallMax = 2500, semFoco = true } = {}) {
  await esp(); await scrollar(scroll); await esp(250);
  const navTop = await p.evaluate(() => document.querySelector("nav.mob-nav").getBoundingClientRect().top);
  await p.screenshot({ path: `${OUT}${nome}.png` });
  const m = { img: `${nome}.png`, w: 390, h: 844, hdr: 95.78, barTop: +navTop.toFixed(1), navTop: +navTop.toFixed(1), scroll, alvos: await caixas(alvos) };
  m.alvosN = m.alvos;
  if (tall) {
    await p.setViewportSize({ width: 390, height: tallMax }); await esp(500);
    const fim = await p.evaluate((lim) => { let m = 0; document.querySelectorAll("main *").forEach((e) => { const r = e.getBoundingClientRect(); if (r.height && r.bottom < lim - 50) m = Math.max(m, r.bottom); }); return m; }, tallMax);
    const H = Math.max(844, Math.ceil(fim + 24 + 69));
    await p.setViewportSize({ width: 390, height: H }); await esp(500);
    await p.screenshot({ path: `${OUT}${nome}_tall.png` });
    m.tall = { img: `${nome}_tall.png`, h: H, alvos: await caixas(alvos) };
    await p.setViewportSize({ width: 390, height: 844 }); await esp(500);
  }
  mapa[nome] = m; console.log(nome, tall ? `tall H=${m.tall.h}` : "", scroll ? `scroll=${scroll}` : "", "barTop", m.barTop);
}
const campo = (rot) => `div:has(> label:text-is("${rot}"))`;
const R = { por: "Lançar por", vaca: "Vaca em lactação (nº / nome)", lote: "Lote", data: "Data do controle", o1: "1ª ordenha (kg)", o2: "2ª ordenha (kg)", o3: "3ª ordenha (kg, opcional)" };
const BUSCA = 'input[placeholder="Buscar vaca em lactação…"]';
const ALV = {
  por: campo(R.por), btnVaca: campo(R.por) + ' button:text-is("Vaca")', btnLote: campo(R.por) + ' button:text-is("Lote")',
  campoVaca: campo(R.vaca), busca: BUSCA, res4746: 'button.mob-btn-2:has-text("4746")', lista: BUSCA + " ~ div, div:has(> div > " + BUSCA + ") + div",
  selecionada: campo(R.vaca) + " > button", campoLote: campo(R.lote), loteSel: campo(R.lote) + " select", data: campo(R.data), dataIn: campo(R.data) + " input",
  o1: campo(R.o1), o1In: campo(R.o1) + " input", o2: campo(R.o2), o2In: campo(R.o2) + " input", o3: campo(R.o3), o3In: campo(R.o3) + " input",
  total: "p:has-text('Total do dia')", salvar: 'button.mob-btn:text-is("Salvar")', aviso: 'p:has-text("Lançamento salvo.")', rascunho: "p:has-text('Rascunho salvo')",
};
const cartao = (n) => `div.mob-input:has(> div:text-is("Nº ${n}"))`;   // é ajustado abaixo (o texto inclui o DEL)
const cart = (i) => `div.mob-input:has(> div > input) >> nth=${i}`;
const resumoLote = "div:has(> span:has-text('vaca(s) do lote'))";
const ALV_L = (extra = {}) => ({
  ...ALV, resumo: resumoLote, qtd: "span:has-text('vaca(s) do lote')", totalLote: "span:has-text('Total:')", ...extra,
  ...Object.fromEntries([0, 1, 2, 3].flatMap((i) => [[`c${i}`, cart(i)], [`c${i}h`, cart(i) + " > div:first-child"],
    [`c${i}a`, cart(i) + " input >> nth=0"], [`c${i}b`, cart(i) + " input >> nth=1"], [`c${i}c`, cart(i) + " input >> nth=2"]])),
});

// ───────────── Por vaca ─────────────
({ p } = await sessao());
await p.goto("http://localhost:3000/app/lancar", { waitUntil: "networkidle" }); await esp(1400);
await snap("s01_lancar", { alvos: { prod: "button.mob-bloco:has-text('Produção (Leite)')", navLancar: "nav.mob-nav >> text=Lançar" } });
await p.locator("button.mob-bloco", { hasText: "Produção (Leite)" }).first().click(); await esp(600);
await snap("s02_prod_grade", { alvos: { controle: "button.mob-bloco:has-text('Controle leiteiro')", pesagem: "button.mob-bloco:has-text('Pesagem corporal')", grade: ".mob-bloco >> nth=0" } });
await p.locator("button.mob-bloco", { hasText: "Controle leiteiro" }).first().click(); await esp(1300);
await snap("s03_vaca_busca", { tall: true, alvos: ALV });
await p.fill(BUSCA, "4746"); await esp(500);
await snap("s04_digitado", { tall: true, alvos: ALV });
await p.locator("button.mob-btn-2", { hasText: "4746" }).first().click(); await esp(600);
await snap("s05_selecionada", { tall: true, alvos: ALV });
await p.fill(campo(R.o1) + " input", "18.4"); await esp(400);
await snap("s06_o1", { tall: true, alvos: ALV });
await p.fill(campo(R.o2) + " input", "16.2"); await esp(500);
await snap("s07_o2_total", { tall: true, alvos: ALV });
await cfg({ atraso: 500 });
await p.locator(ALV.salvar).scrollIntoViewIfNeeded();
await p.locator(ALV.salvar).click();
await p.waitForSelector(ALV.aviso, { timeout: 15000 }); await esp(600);
await snap("s08_salvo", { tall: true, alvos: ALV });

// ───────────── Por lote ─────────────
await scrollar(0); await esp(300);
await p.locator(ALV.btnLote).click(); await esp(600);
await snap("s09_lote_vazio", { tall: true, alvos: ALV_L() });
await p.selectOption(campo(R.lote) + " select", "01 - Alta"); await esp(800);
await snap("s10_lote_cartoes", { tall: true, alvos: ALV_L() });
await p.fill(cart(0) + " input >> nth=0", "22.1"); await p.fill(cart(0) + " input >> nth=1", "19.8"); await esp(500);
await snap("s11_vaca1", { tall: true, alvos: ALV_L() });
await p.fill(cart(1) + " input >> nth=0", "15.0"); await p.fill(cart(1) + " input >> nth=1", "14.2"); await esp(500);
await snap("s12_vaca2", { tall: true, alvos: ALV_L() });
await p.fill(cart(2) + " input >> nth=0", "20.5"); await esp(500);
await snap("s13_vaca3_vazio", { tall: true, alvos: ALV_L() });
// fim da página: Salvar (normal e alta, mesma posição) — lote inteiro numa captura só, com escala reduzida se preciso
await p.locator(ALV.salvar).scrollIntoViewIfNeeded(); await esp(300);
const mx = await maxScroll(); console.log("maxScroll lote", mx);
await snap("s14_fim_lote", { alvos: ALV_L(), scroll: mx });
await p.locator(ALV.salvar).click();
await p.waitForSelector(ALV.aviso, { timeout: 15000 }); await esp(700);
await snap("s15_salvo_lote", { alvos: ALV_L(), scroll: await maxScroll() });
const log = await (await fetch(API + "/__log")).json(); console.log("POSTs:", JSON.stringify(log.filter((x) => x.p === "/producao/controles").map((x) => x.b)));
fs.writeFileSync("mapa.json", JSON.stringify(mapa, null, 1));
await br.close();
