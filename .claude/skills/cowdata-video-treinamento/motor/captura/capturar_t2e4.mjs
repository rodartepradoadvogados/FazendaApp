// Temporada 2 · Ep. 4 — Reprodutivo › Parto. Captura as telas REAIS do app (produção) contra o stub (EP=t2e4).
// Rodar:  EP=t2e4 node stub-api.mjs &   (frontend: next start)   node capturar_t2e4.mjs
import fs from "fs";
import { chromium, novoContexto, pagina } from "./lib.mjs";
const OUT = "shots/"; fs.mkdirSync(OUT, { recursive: true }); const mapa = {};
const API = "http://localhost:8000";
const br = await chromium.launch({ args: ["--lang=pt-BR"], env: { ...process.env, LANGUAGE: "pt_BR", LC_ALL: "pt_BR.UTF-8", LANG: "pt_BR.UTF-8" } });

async function sessao() {
  await fetch(API + "/__reset");
  const ctx = await novoContexto(br);
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
// O Parto não tem barra fixa de ação (o Salvar fica no fim do formulário): barTop = topo da navegação.
// tall = captura alta (viewport grande) para o motor rolar a imagem; scroll = posição da página na captura normal
async function snap(nome, { tall = false, alvos = {}, scroll = 0, tallMax = 3000 } = {}) {
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
const R = { matriz: "Matriz (nº / nome)", data: "Data do parto", tipo: "Tipo de parto", ret: "Retenção de placenta", gem: "Parto gemelar (2 crias)", sexo: "Sexo da cria",
  num: "Número da cria (opcional — vazio = baixa automática)", baixada: "Cria baixada? (não entra no rebanho)", tomou: "Tomou colostro?", litros: "Quantidade de colostro (litros)", brix: "Brix do colostro (%)" };
const ALV = {
  matriz: campo(R.matriz), matrizBtn: campo(R.matriz) + " > button", data: campo(R.data), dataIn: campo(R.data) + " input",
  tipo: campo(R.tipo), tipoSel: campo(R.tipo) + " select",
  ret: campo(R.ret), retChk: campo(R.ret) + " label", retCx: campo(R.ret) + " input",
  gem: campo(R.gem), gemChk: campo(R.gem) + " label", gemCx: campo(R.gem) + " input",
  sexo: campo(R.sexo), btnF: campo(R.sexo) + ' button:has-text("Fêmea")', btnM: campo(R.sexo) + ' button:has-text("Macho")',
  num: campo(R.num), numRot: campo(R.num) + " > label", numIn: campo(R.num) + " input",
  baixada: campo(R.baixada), btnColo: 'button.mob-btn-2:has-text("Colostragem e IgG")',
  tomou: campo(R.tomou), tomouSim: campo(R.tomou) + ' button:text-is("Sim")', litros: campo(R.litros), litrosSel: campo(R.litros) + " select",
  brix: campo(R.brix), brixSel: campo(R.brix) + " select", brixCls: campo(R.brix) + " p",
  salvar: 'button.mob-btn:text-is("Salvar")', aviso: 'p:has-text("Lançamento salvo.")',
};
const ALV_G = { ...ALV, gemSexos: campo("Sexos do parto gemelar"), sec2: 'div.mob-secao:text-is("2ª cria")', sexo2: campo("Sexo da 2ª cria"), btnF2: campo("Sexo da 2ª cria") + ' button:has-text("Fêmea")', num2: campo("Número da 2ª cria"), num2In: campo("Número da 2ª cria") + " input", baixada2: campo("2ª cria baixada?") };
const MOD = { modal: '[role="dialog"]', titulo: '[role="dialog"] h2', texto: '[role="dialog"] > div:nth-of-type(2)', forte: '[role="dialog"] strong', lote: '[role="dialog"] strong >> nth=1', confirmar: '[role="dialog"] button.mob-btn', cancelar: '[role="dialog"] button.mob-btn-2' };
const AV = { aviso: 'p:has-text("Lançamento salvo.")', aviso1: 'p:has-text("3654 movido para o lote 01 - Alta.")', aviso2: 'p:has-text("4712 movido para o lote 07 - Bezerras.")' };

async function irParaParto() {
  await p.goto("http://localhost:3000/app/lancar", { waitUntil: "networkidle" }); await esp(1400);
}
// ───────────── O fluxo feliz: 3654 pare uma fêmea (4712) ─────────────
({ p } = await sessao());
await irParaParto();
await snap("s01_lancar", { alvos: { repro: "button.mob-bloco:has-text('Reprodutivo')", navLancar: "nav.mob-nav >> text=Lançar" } });
await p.locator("button.mob-bloco", { hasText: "Reprodutivo" }).first().click(); await esp(500);
await snap("s02_repro_grade", { alvos: { parto: "button.mob-bloco:has-text('Parto')", diagnostico: "button.mob-bloco:has-text('Diagnóstico')" } });
await p.locator("button.mob-bloco", { hasText: "Parto" }).first().click(); await esp(1500);
const BUSCA = { busca: 'input[placeholder="Buscar matriz…"]', lista: 'input[placeholder="Buscar matriz…"] ~ div, div:has(> div > input[placeholder="Buscar matriz…"]) + div' };
await snap("s03_parto_busca", { alvos: { ...BUSCA, matriz: campo(R.matriz) } });
await p.fill('input[placeholder="Buscar matriz…"]', "3654"); await esp(400);
await snap("s04_digitado", { alvos: { ...BUSCA, res3654: 'button.mob-btn-2:has-text("3654")' } });
await p.locator('button.mob-btn-2', { hasText: "3654" }).first().click(); await esp(500);
await snap("s05_matriz", { tall: true, alvos: ALV });
await p.selectOption(campo(R.tipo) + " select", "Normal"); await esp(300);
await snap("s06_tipo", { tall: true, alvos: ALV });
await p.locator(campo(R.sexo) + ' button:has-text("Fêmea")').click(); await esp(300);
await snap("s07_sexo", { tall: true, alvos: ALV });
await p.fill(campo(R.num) + " input", "4712"); await esp(300);
await snap("s08_numero", { tall: true, alvos: ALV });
await p.locator(ALV.btnColo).click(); await esp(500);
await snap("s09_colo", { tall: true, alvos: ALV });
await p.locator(ALV.tomouSim).click(); await esp(300);
await snap("s10_tomou", { tall: true, alvos: ALV });
await p.selectOption(ALV.litrosSel, "4"); await esp(300);
await snap("s11_litros", { tall: true, alvos: ALV });
await p.selectOption(ALV.brixSel, "27"); await esp(400);
await snap("s12_brix", { tall: true, alvos: ALV });
// Salvar → "Lançamento salvo." + modal da mãe
await p.locator(ALV.salvar).scrollIntoViewIfNeeded();
await p.locator(ALV.salvar).click();
await p.waitForSelector('[role="dialog"]', { timeout: 8000 }); await esp(400);
const yS = await p.evaluate(() => { const b = [...document.querySelectorAll("button.mob-btn")].find((e) => e.textContent.trim() === "Salvar"); return Math.round(b.getBoundingClientRect().top + window.scrollY); });
const scrollModal = Math.max(0, yS - 150);
await snap("s13_modal_mae", { alvos: { ...MOD, ...AV }, scroll: scrollModal });
await p.locator(MOD.confirmar).click(); await esp(500);
await p.waitForFunction(() => document.body.innerText.includes("Alocar a cria"), null, { timeout: 8000 });
await snap("s14_modal_cria", { alvos: { ...MOD, ...AV }, scroll: scrollModal });
await p.locator(MOD.confirmar).click(); await esp(500);
await p.waitForFunction(() => document.body.innerText.includes("4712 movido"), null, { timeout: 8000 });
await snap("s15_final", { alvos: { ...AV }, scroll: scrollModal });
const log = await (await fetch(API + "/__log")).json(); console.log("LOG:", log.map((x) => x.p + " " + JSON.stringify(x.b).slice(0, 220)).join("\n  "));

// ───────────── Gêmeos (formulário novo, nada é salvo) ─────────────
await p.context().close();
({ p } = await sessao());
await irParaParto();
await p.locator("button.mob-bloco", { hasText: "Reprodutivo" }).first().click(); await esp(500);
await p.locator("button.mob-bloco", { hasText: "Parto" }).first().click(); await esp(1200);
await p.fill('input[placeholder="Buscar matriz…"]', "5611"); await esp(400);
await p.locator('button.mob-btn-2', { hasText: "5611" }).first().click(); await esp(500);
await p.selectOption(campo(R.tipo) + " select", "Normal"); await esp(300);
await snap("s16_novo", { tall: true, alvos: ALV_G });
await p.locator(campo(R.gem) + " input").check(); await esp(400);
await snap("s17_gemelar", { tall: true, alvos: ALV_G });
await p.locator(campo(R.sexo) + ' button:has-text("Fêmea")').click(); await p.fill(campo(R.num) + " input", "4720");
await p.locator(ALV_G.btnF2).click(); await p.fill(campo("Número da 2ª cria") + " input", "4721"); await esp(400);
await snap("s18_gemelar2", { tall: true, alvos: ALV_G });
fs.writeFileSync("mapa.json", JSON.stringify(mapa, null, 1));
await br.close();
